"""Conservative AI suggestions for historical post classification.

Only editorial text enters the model prompt. Performance metrics are deliberately
absent so that labels cannot be influenced by a post's observed results.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Protocol

from easel.ai_service import AIService, AIRuntimeStatus, ConfiguredAIService
from .historical import HistoricalPostService
from .repository import CONTENT_TYPE_LABELS, SUBJECT_LABELS, OperatorAccountRepository

CONTENT_SOURCE_VALUES = {"REAL", "AI", "MIXED", "UNKNOWN"}
CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW"}
CLASSIFICATION_FIELDS = ("content_source", "subjects", "content_type")

CLASSIFICATION_PROMPT = """你是历史作品标签建议器，只负责分类，不提供任何运营策略。
你只能依据每条作品提供的标题、平台原始作品类型、已有标签和描述。输入中不包含表现数据；不得推断或讨论播放、点赞等表现。

标签约束：
- content_source 只能是 REAL、AI、MIXED、UNKNOWN。仅凭标题不能可靠判断是真拍还是 AI 时必须 UNKNOWN；明确写有“AI生成”“AI视频”“AI创作”等来源证据才可判 AI，单独的 #AI / #ai 或“剪映”标签不够；明确写实拍/真人与 AI 混合可对应 REAL/MIXED。不要仅因内容看起来可爱或不寻常而猜来源。
- subjects 只能是“缅因”“布偶”“双猫”“其他”“UNKNOWN”。标题/标签明确同时出现两猫、双猫或缅因与布偶时用“双猫”；明确单一品种用该品种。没有明确证据必须 UNKNOWN。不能由猫的外观推断品种。
- content_type 只能是“单猫日常”“双猫互动”“双猫反差”“搞笑/趣味”“养猫经验”“情绪/陪伴”“AI创意”“其他”。只有文本线索足够明确才选具体类别，否则 UNKNOWN。“单猫日常”必须明确描述一只具体猫的行为/生活；笼统的“猫咪日常”“萌宠日常”不能推断只有一只猫。双猫互动必须同时有明确的两只猫主体和相互打闹、追逐、抢东西、依偎等互动动作；仅同时提到缅因和布偶、出现“玩不起”等模糊词不能推出互动。双猫反差必须明确描述两只猫的不同性格或相反行为。“情绪/陪伴”必须明确表达与猫共同生活、陪伴、治愈、依恋等关系；仅有泛化的情绪化修辞不够。清晰的趣味行为或“整活/搞怪/迷惑行为”等直接文本线索可以支持“搞笑/趣味”。
- 每个字段独立给 confidence：明确文本直接支持为 HIGH；文本强烈暗示但有推断为 MEDIUM；弱猜测或 UNKNOWN 为 LOW。不要为了覆盖率提高置信度。
- reason 可空，最多 20 个汉字，只说明标签证据，不谈表现。

严格只返回 JSON，不要 Markdown。格式：
{"classifications":[{"post_id":"原样返回","content_source":{"value":"UNKNOWN","confidence":"LOW","reason":""},"subjects":{"value":"UNKNOWN","confidence":"LOW","reason":""},"content_type":{"value":"UNKNOWN","confidence":"LOW","reason":""}}]}
每个输入 post_id 必须且只返回一次。"""

SUBJECTS_ONLY_PROMPT = """你只判断每条历史作品的出镜主体，不判断内容来源、内容类型、Hook、表现或运营建议。
只根据提供的 title、source_content_type、tags、description 里的明确文字判断。
主体只能是“缅因”“布偶”“双猫”“其他”“UNKNOWN”。明确提到缅因或布偶时选相应品种；明确提到两只猫、双猫，或同时明确提到缅因与布偶时选“双猫”。“其他”仅用于文本明确指出出镜主体属于其他动物/人物等非上述猫咪主体；笼统的“我的猫/小猫”不能据此归入“其他”。
“哥哥/妹妹”仅在输入文本明确同时给出既有品种映射时才可用于推断。泛称“猫咪/小猫/萌宠”、模糊代词、视频体裁均不足以确定品种或数量，必须返回 UNKNOWN。不要为了覆盖率猜测。
confidence：直接明确文本为 HIGH；存在有限但可靠文本暗示为 MEDIUM；UNKNOWN 为 LOW。reason 最多 20 个汉字，只说明文本证据。
严格只返回 JSON：{"classifications":[{"post_id":"原样返回","subjects":{"value":"UNKNOWN","confidence":"LOW","reason":""}}]}。每个输入 post_id 必须且只返回一次。"""


class ClassificationModel(Protocol):
    def classify_batch(self, posts: list[dict]) -> list[dict]: ...


class ClassificationUnavailable(RuntimeError):
    pass


class AIServiceHistoricalClassifier:
    """Adapt the provider-neutral chat service to historical editorial labels."""

    def __init__(self, ai_service: AIService | None = None) -> None:
        self.ai_service = ai_service or ConfiguredAIService()

    @staticmethod
    def _parse_json(text: str) -> dict:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                raise ValueError("model_returned_invalid_json")
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError("model_returned_invalid_json") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("classifications"), list):
            raise ValueError("model_returned_invalid_schema")
        return parsed

    @staticmethod
    def _normalize_item(raw: dict, post_id: str, fields: tuple[str, ...] = CLASSIFICATION_FIELDS) -> dict:
        output = {"post_id": post_id}
        allowed = {
            "content_source": CONTENT_SOURCE_VALUES,
            "subjects": SUBJECT_LABELS,
            "content_type": CONTENT_TYPE_LABELS | {"UNKNOWN"},
        }
        for field in fields:
            valid_values = allowed[field]
            item = raw.get(field) if isinstance(raw, dict) else None
            item = item if isinstance(item, dict) else {}
            value = str(item.get("value", "UNKNOWN")).strip()
            confidence = str(item.get("confidence", "LOW")).strip().upper()
            if value not in valid_values:
                value = "UNKNOWN"
                confidence = "LOW"
            if value == "UNKNOWN":
                confidence = "LOW"
            if confidence not in CONFIDENCE_VALUES:
                confidence = "LOW"
            reason = str(item.get("reason") or "").strip()[:20]
            output[field] = {"value": value, "confidence": confidence, "reason": reason}
        return output

    def runtime_status(self) -> AIRuntimeStatus:
        return self.ai_service.runtime_status()

    def classify_batch(self, posts: list[dict], fields: tuple[str, ...] = CLASSIFICATION_FIELDS) -> list[dict]:
        if not posts:
            return []
        fields = tuple(fields)
        if not fields or set(fields) - set(CLASSIFICATION_FIELDS):
            raise ValueError("请选择有效的分类字段")
        try:
            text = self.ai_service.complete(
                SUBJECTS_ONLY_PROMPT if fields == ("subjects",) else CLASSIFICATION_PROMPT,
                json.dumps({"posts": posts}, ensure_ascii=False),
            )
        except Exception as exc:  # one bad response must not discard other batches
            return [{"post_id": str(post["post_id"]), "status": "FAILED",
                     "failure": type(exc).__name__} for post in posts]
        try:
            parsed = self._parse_json(text)
        except ValueError as exc:
            # A malformed batch response has no reliable row-to-result mapping.
            # Retry smaller editorial-only batches so a single broken item does
            # not discard valid neighboring suggestions; only the bad singleton
            # is ultimately marked failed.
            if len(posts) > 1:
                midpoint = len(posts) // 2
                return (self.classify_batch(posts[:midpoint], fields)
                        + self.classify_batch(posts[midpoint:], fields))
            return [{"post_id": str(posts[0]["post_id"]), "status": "FAILED",
                     "failure": type(exc).__name__}]

        input_ids = [str(post["post_id"]) for post in posts]
        input_set = set(input_ids)
        found: dict[str, dict] = {}
        duplicates: set[str] = set()
        for item in parsed["classifications"]:
            if not isinstance(item, dict):
                continue
            post_id = str(item.get("post_id", ""))
            if post_id not in input_set:
                continue
            if post_id in found:
                duplicates.add(post_id)
                continue
            if not all(isinstance(item.get(field), dict) for field in fields):
                found[post_id] = {"post_id": post_id, "status": "FAILED", "failure": "invalid_item_schema"}
                continue
            normalized = self._normalize_item(item, post_id, fields)
            if any(normalized[field]["value"] == "UNKNOWN" and
                   str(item[field].get("value", "UNKNOWN")).strip() != "UNKNOWN"
                   for field in fields):
                found[post_id] = {"post_id": post_id, "status": "FAILED", "failure": "invalid_label"}
                continue
            found[post_id] = {**normalized, "status": "OK"}
        for post_id in duplicates:
            found[post_id] = {"post_id": post_id, "status": "FAILED", "failure": "duplicate_item"}
        for post_id in input_ids:
            found.setdefault(post_id, {"post_id": post_id, "status": "FAILED", "failure": "missing_item"})
        return [found[post_id] for post_id in input_ids]


class HistoricalClassificationService:
    # This provider takes close to a minute for five records; keep each request
    # comfortably below the configured 60-second HTTP timeout.
    BATCH_SIZE = 5

    def __init__(self, repository: OperatorAccountRepository | None = None, *,
                 model: ClassificationModel | None = None, ai_service: AIService | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.posts = HistoricalPostService(self.repository)
        self.model = model or AIServiceHistoricalClassifier(ai_service)

    def runtime_status(self) -> AIRuntimeStatus:
        status = getattr(self.model, "runtime_status", None)
        if callable(status):
            return status()
        # Injected test/deterministic models represent an available runtime.
        from easel.ai_service import AIRuntimeState
        return AIRuntimeStatus(AIRuntimeState.AVAILABLE, "当前模型")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def suggest(self, account_id: str, fields: list[str] | None = None) -> dict:
        requested_fields = tuple(fields or CLASSIFICATION_FIELDS)
        if not requested_fields or set(requested_fields) - set(CLASSIFICATION_FIELDS):
            raise ValueError("请选择有效的分类字段")
        rows = self.posts.canonical_posts(account_id)
        overlay = self.repository.get_classification_overlay(account_id, [row["id"] for row in rows])
        candidates = []
        targets: dict[str, set[str]] = {}
        for row in rows:
            metadata = overlay[row["id"]]["metadata"]
            suggestions = overlay[row["id"]]["suggestions"]
            target_fields = set()
            for field in requested_fields:
                if metadata.get(field, {}).get("source") == "MANUAL_CONFIRMED":
                    continue
                value = (row.get("content_source") if field == "content_source" else
                         row.get("subjects") if field == "subjects" else row.get("content_type"))
                is_unknown = (not value or value == "UNKNOWN" or value == [])
                # Unknowns are deliberately eligible for a fresh suggestion even
                # when an earlier low-confidence UNKNOWN suggestion is stored.
                if is_unknown:
                    target_fields.add(field)
            if not target_fields:
                continue
            targets[row["id"]] = target_fields
            # Intentionally whitelist editorial inputs. Never add performance metrics here.
            candidates.append({
                "post_id": row["id"],
                "title": row.get("title") or "",
                "source_content_type": row.get("content_type_raw") or row.get("content_type") or "",
                "tags": row.get("tags") or [],
                "description": row.get("note") or "",
            })
        results: dict[str, dict] = {}
        failed_posts: set[str] = set()
        for start in range(0, len(candidates), self.BATCH_SIZE):
            batch = candidates[start:start + self.BATCH_SIZE]
            try:
                if isinstance(self.model, AIServiceHistoricalClassifier):
                    items = self.model.classify_batch(batch, requested_fields)
                else:
                    items = self.model.classify_batch(batch)
            except Exception:  # a provider error affects this batch only
                failed_posts.update(str(row["post_id"]) for row in batch)
                continue
            batch_ids = {str(row["post_id"]) for row in batch}
            for item in items:
                post_id = str(item.get("post_id", ""))
                if post_id not in batch_ids or item.get("status") == "FAILED":
                    if post_id in batch_ids:
                        failed_posts.add(post_id)
                    continue
                item = dict(item)
                item.pop("post_id", None)
                item.pop("status", None)
                # The model returns a complete schema, but only persist fields
                # that are still unresolved. This prevents a retry from creating
                # a conflicting suggestion for a previously confirmed field.
                results[post_id] = {field: value for field, value in item.items()
                                    if field in targets.get(post_id, set())}
            failed_posts.update(batch_ids - {str(item.get("post_id", "")) for item in items})
        self.repository.save_classification_suggestions(account_id, results, self._now())
        stored = self.repository.get_classification_overlay(account_id, list(results))
        suggested_fields = sum(len(item["suggestions"]) for item in stored.values())
        high_fields = sum(field.get("confidence") == "HIGH" for item in stored.values()
                          for field in item["suggestions"].values())
        suggested_posts = sum(bool(item["suggestions"]) for item in stored.values())
        return {"suggested_post_count": suggested_posts, "suggested_field_count": suggested_fields,
                "high_confidence_field_count": high_fields, "failed_post_count": len(failed_posts)}

    def classification_rows(self, account_id: str) -> list[dict]:
        rows = self.posts.canonical_posts(account_id)
        overlays = self.repository.get_classification_overlay(account_id, [row["id"] for row in rows])
        result = []
        for row in rows:
            model = self.posts._to_model(row).as_dict()
            overlay = overlays[row["id"]]
            # Older requests may have left a pending suggestion beside a value
            # that has since been confirmed. Keep the review UI focused on open
            # fields so stale suggestions cannot contradict the saved label.
            current_values = {"content_source": model.get("content_source"),
                              "subjects": model.get("subjects"),
                              "content_type": model.get("content_type")}
            for field in list(overlay["suggestions"]):
                value = current_values[field]
                resolved = (bool(value) and value not in ("UNKNOWN", []))
                if resolved:
                    overlay["suggestions"].pop(field, None)
            if not overlay["suggestions"]:
                overlay["suggestion_status"] = None
            result.append({**model, **overlay})
        return result

    def progress(self, account_id: str) -> dict:
        rows = self.posts.canonical_posts(account_id)
        total = len(rows)
        count_source = sum(row.get("content_source") not in (None, "UNKNOWN") for row in rows)
        count_subjects = sum(any(subject in SUBJECT_LABELS - {"UNKNOWN"} for subject in (row.get("subjects") or []))
                             for row in rows)
        count_type = sum(row.get("content_type") in CONTENT_TYPE_LABELS for row in rows)
        def metric(count: int) -> dict:
            return {"classified_count": count, "sample_size": total,
                    "coverage": round(count / total, 4) if total else 0}
        return {"sample_size": total, "content_source": metric(count_source),
                "subjects": metric(count_subjects), "content_type": metric(count_type)}

    def accept(self, account_id: str, post_ids: list[str], fields: list[str], *,
               high_confidence_only: bool = False) -> dict[str, int]:
        return self.repository.accept_classification_suggestions(
            account_id, post_ids, fields, self._now(), high_confidence_only=high_confidence_only,
        )
