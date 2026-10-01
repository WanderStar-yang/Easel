"""Deterministic, account-scoped Weekly Review and human-confirmed Strategy Memory."""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from easel.ai_service import AIRuntimeState, AIService, ConfiguredAIService

from .baselines import AccountBaselineService
from .feedback_repository import OperatorFeedbackRepository
from .repository import AccountNotFoundError, OperatorAccountRepository

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
METRIC_FIELDS = ("views", "likes", "comments", "favorites", "shares", "followers_gain", "profile_visits", "inquiries")
INTERACTIONS = ("likes", "comments", "favorites", "shares")
CHECKPOINT_RANK = {"24H": 1, "72H": 2, "7D": 3}


def _median(values: list[float | int]) -> float | int | None:
    return statistics.median(values) if values else None


def _percentile(values: list[float | int], p: float) -> float | int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int((len(ordered) - 1) * p + 0.5)))]


def _engagement(row: dict[str, Any]) -> float | None:
    views = row.get("views")
    available = [row.get(field) for field in INTERACTIONS if row.get(field) is not None]
    if not isinstance(views, (int, float)) or views <= 0 or not available:
        return None
    return sum(available) / views


class WeeklyReviewService:
    def __init__(self, repository: OperatorAccountRepository | None = None, *,
                 feedback: OperatorFeedbackRepository | None = None,
                 baselines: AccountBaselineService | None = None,
                 ai: AIService | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.repository.initialize()
        self.feedback = feedback or OperatorFeedbackRepository(self.repository)
        self.baselines = baselines or AccountBaselineService(self.repository)
        self.ai = ai or ConfiguredAIService()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(LOCAL_TIMEZONE)

    @staticmethod
    def _timestamp(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("时间格式无效，请使用 ISO 日期时间。") from exc
        if parsed.tzinfo is None:
            raise ValueError("发布时间必须包含时区信息。")
        return parsed.astimezone(LOCAL_TIMEZONE).isoformat(timespec="seconds")

    def context(self, account_id: str) -> dict[str, Any]:
        return self.feedback.context(account_id)

    def register_published_post(self, account_id: str, *, topic_id: str, draft_id: str | None,
                                values: dict[str, Any]) -> dict[str, Any]:
        try:
            title = str(values.get("title") or "").strip()
            if not title or len(title) > 200:
                raise ValueError("标题为必填项，最多 200 个字。")
            source = values.get("content_source")
            if source not in {"REAL", "AI", "MIXED", "UNKNOWN"}:
                raise ValueError("内容来源必须是 REAL、AI、MIXED 或 UNKNOWN。")
            if values.get("duration_seconds") is not None and int(values["duration_seconds"]) <= 0:
                raise ValueError("作品时长必须大于 0 秒。")
            platform_post_id = str(values.get("platform_post_id") or "").strip() or None
            normalized = {**values, "title": title, "platform_post_id": platform_post_id,
                          "published_at": self._timestamp(values["published_at"])}
            return self.feedback.create_published_post(account_id, topic_id, draft_id, normalized,
                                                       self._now().isoformat())
        except AccountNotFoundError:
            raise

    def record_metrics(self, account_id: str, post_id: str, checkpoint: str, values: dict[str, Any]) -> dict[str, Any]:
        if checkpoint not in CHECKPOINT_RANK:
            raise ValueError("数据节点必须是 24H、72H 或 7D。")
        if not any(values.get(field) is not None for field in METRIC_FIELDS):
            raise ValueError("至少填写一个实际指标；未知字段请留空，真实 0 请填写 0。")
        for field in METRIC_FIELDS:
            value = values.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"{field} 必须是整数或留空。")
            if field != "followers_gain" and value is not None and value < 0:
                raise ValueError(f"{field} 不能小于 0。")
        return self.feedback.save_metric(account_id, post_id, checkpoint, values,
                                         self._now().isoformat(timespec="seconds"))

    @staticmethod
    def _baseline_metric(baseline: dict[str, Any] | None, field: str) -> dict[str, Any] | None:
        if not baseline or baseline.get("status") != "ACTIVE":
            return None
        try:
            return baseline["metrics"][field]
        except (KeyError, TypeError):
            return None

    @classmethod
    def _metric_summary(cls, rows: list[dict[str, Any]], baseline: dict[str, Any] | None) -> dict[str, Any]:
        output: dict[str, Any] = {}
        values_by_field: dict[str, list[float | int]] = {
            field: [row[field] for row in rows if isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool)]
            for field in METRIC_FIELDS
        }
        values_by_field["engagement_rate"] = [value for row in rows if (value := _engagement(row)) is not None]
        denominator = len(rows)
        for field, values in values_by_field.items():
            ref = cls._baseline_metric(baseline, field)
            ref_median = ref.get("median") if isinstance(ref, dict) else None
            median = _median(values)
            relative = ((median - ref_median) / abs(ref_median)
                        if isinstance(median, (int, float)) and isinstance(ref_median, (int, float)) and ref_median != 0
                        else (0.0 if median == 0 and ref_median == 0 else None))
            output[field] = {
                "median": median, "p25": _percentile(values, 0.25), "p75": _percentile(values, 0.75),
                "sample_count": len(values), "coverage": round(len(values) / denominator, 4) if denominator else 0,
                "baseline_median": ref_median, "relative_to_baseline": relative,
            }
        return output

    @classmethod
    def _groups(cls, rows: list[dict[str, Any]], baseline: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
        dimensions: dict[str, dict[str, list[dict[str, Any]]]] = {
            "content_pillar": {}, "topic": {}, "content_source": {}, "hook_type": {},
            "duration_bucket": {}, "publish_period": {},
        }
        for row in rows:
            labels = {
                "content_pillar": (row.get("pillar_id"), row.get("pillar_name")),
                "topic": (row.get("topic_id"), row.get("topic_title")),
                "content_source": (row.get("content_source"), row.get("content_source")),
                "hook_type": (row.get("hook_type"), row.get("hook_type")),
                "duration_bucket": (cls._duration_bucket(row.get("duration_seconds")), cls._duration_bucket(row.get("duration_seconds"))),
                "publish_period": (cls._publish_period(row.get("published_at")), cls._publish_period(row.get("published_at"))),
            }
            for dimension, (key, label) in labels.items():
                if key is not None and str(key).strip():
                    dimensions[dimension].setdefault(str(key), []).append(row)
        output: dict[str, list[dict[str, Any]]] = {}
        for dimension, groups in dimensions.items():
            output[dimension] = [{"key": key, "label": group[0].get("pillar_name") if dimension == "content_pillar" else (
                group[0].get("topic_title") if dimension == "topic" else cls._group_label(dimension, key, group[0])),
                "sample_size": len(group), "metrics": cls._metric_summary(group, baseline)}
                for key, group in sorted(groups.items())]
        return output

    @staticmethod
    def _duration_bucket(value: int | None) -> str | None:
        if value is None:
            return None
        if value <= 15:
            return "≤15 秒"
        if value <= 30:
            return "16–30 秒"
        if value <= 60:
            return "31–60 秒"
        return ">60 秒"

    @staticmethod
    def _publish_period(value: str | None) -> str | None:
        if not value:
            return None
        try:
            hour = datetime.fromisoformat(value).astimezone(LOCAL_TIMEZONE).hour
        except ValueError:
            return None
        return "早间（6–11）" if 6 <= hour < 11 else "午间（11–14）" if 11 <= hour < 14 else (
            "下午（14–18）" if 14 <= hour < 18 else "晚间（18–24）" if hour >= 18 else "凌晨（0–6）")

    @staticmethod
    def _group_label(dimension: str, key: str, row: dict[str, Any]) -> str:
        if dimension == "content_source":
            return {"REAL": "真实拍摄", "AI": "AI 生成", "MIXED": "真人/AI 混合", "UNKNOWN": "无法判断"}.get(key, key)
        return key

    @staticmethod
    def _latest_per_post(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        for post in posts:
            available = post.get("metrics") or []
            if not available:
                continue
            latest = max(available, key=lambda item: (CHECKPOINT_RANK.get(item["checkpoint"], 0), item.get("recorded_at", "")))
            output.append({**post, **latest, "selected_checkpoint": latest["checkpoint"]})
        return output

    @staticmethod
    def _source_version(posts: list[dict[str, Any]]) -> str:
        payload = json.dumps(posts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _memory_candidates(week_start: str, checkpoint_rows: list[dict[str, Any]],
                           baseline: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not baseline or baseline.get("status") != "ACTIVE":
            return []
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in checkpoint_rows:
            pillar_id = row.get("pillar_id")
            if pillar_id:
                groups.setdefault(str(pillar_id), []).append(row)
        candidates = []
        for pillar_id, rows in groups.items():
            if len(rows) < 3:
                continue
            metrics = WeeklyReviewService._metric_summary(rows, baseline)
            for field in ("views", "engagement_rate"):
                item = metrics[field]
                delta = item.get("relative_to_baseline")
                if not isinstance(delta, (int, float)) or abs(delta) < 0.2:
                    continue
                direction = "above" if delta > 0 else "below"
                name = str(rows[0].get("pillar_name") or "该内容方向")
                metric_name = "播放" if field == "views" else "互动率"
                baseline_value = item.get("baseline_median")
                observed = item.get("median")
                statement = (f"{week_start} 周的“{name}”方向有 {len(rows)} 条作品进入 7D 数据，{metric_name}中位数为 {observed}，"
                             f"相对历史基准 {baseline_value} {delta:+.0%}。这是描述性观察，后续周期应继续验证，不代表内容方向导致了差异。")
                candidates.append({
                    "id": f"memory-{uuid4().hex}",
                    "memory_key": f"pillar:{pillar_id}:{field}:{direction}",
                    "statement": statement,
                    "evidence": {"scope_type": "pillar", "scope_key": pillar_id, "scope_name": name,
                                 "metric": field, "sample_size": len(rows), "median": observed,
                                 "baseline_median": baseline_value, "relative_change": delta,
                                 "published_post_ids": [row["id"] for row in rows], "checkpoint": "7D"},
                })
        return candidates

    def _explain(self, latest_summary: dict[str, Any], pillar_groups: list[dict[str, Any]],
                 fallback_next_steps: list[str]) -> dict[str, Any]:
        facts = {
            "overall_metrics": latest_summary,
            "content_direction_metrics": [
                {"name": item.get("label"), "sample_size": item.get("sample_size"), "metrics": item.get("metrics")}
                for item in pillar_groups
            ],
        }
        try:
            status = self.ai.runtime_status()
            if status.state != AIRuntimeState.AVAILABLE:
                raise RuntimeError("AI runtime unavailable")
            response = self.ai.complete(
                "你负责用普通中文解释周复盘中已经计算好的统计事实。不得重新计算、不得增加输入里没有的数字、不得声称因果。"
                "只返回 JSON：summary（不超过120字）、observations（字符串数组，最多3条）、next_steps（字符串数组，最多3条）。"
                "样本不足时明确说继续积累真实发布数据。",
                json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
            )
            parsed = json.loads(response)
            summary = parsed.get("summary") if isinstance(parsed, dict) else None
            observations = parsed.get("observations") if isinstance(parsed, dict) else None
            next_steps = parsed.get("next_steps") if isinstance(parsed, dict) else None
            if not isinstance(summary, str) or not summary.strip():
                raise ValueError("缺少复盘解释摘要")
            clean_list = lambda value: [item.strip()[:240] for item in value[:3]
                                        if isinstance(item, str) and item.strip()] if isinstance(value, list) else []
            return {"source": "AI", "summary": summary.strip()[:360],
                    "observations": clean_list(observations), "next_steps": clean_list(next_steps) or fallback_next_steps}
        except Exception:  # noqa: BLE001 - keep deterministic review facts available when the model fails.
            return {"source": "LOCAL", "summary": "以下统计由真实发布数据计算；当前无法生成补充文字解释。",
                    "observations": [], "next_steps": fallback_next_steps}

    def generate(self, account_id: str, week_start: str) -> dict[str, Any]:
        try:
            start = date.fromisoformat(week_start)
        except ValueError as exc:
            raise ValueError("请选择有效的周起始日期。") from exc
        if start.weekday() != 0:
            raise ValueError("周复盘的起始日期必须是周一。")
        end = start + timedelta(days=6)
        start_bound = datetime.combine(start, time.min, LOCAL_TIMEZONE).isoformat(timespec="seconds")
        end_bound = datetime.combine(end + timedelta(days=1), time.min, LOCAL_TIMEZONE).isoformat(timespec="seconds")
        posts = self.feedback.posts_for_week(account_id, start_bound, end_bound)
        if not posts:
            raise ValueError("所选周暂无已登记的真实发布作品，不能生成周复盘。")
        baseline_model = self.baselines.latest(account_id)
        baseline = baseline_model.as_dict() if baseline_model else None
        baseline_status = baseline.get("status") if baseline else "MISSING"
        checkpoint_summaries = {}
        groups_by_checkpoint = {}
        for checkpoint in CHECKPOINT_RANK:
            rows = [{**post, **metric, "published_post_id": post["id"]}
                    for post in posts for metric in post.get("metrics", []) if metric["checkpoint"] == checkpoint]
            checkpoint_summaries[checkpoint] = {
                "post_count": len({row["published_post_id"] for row in rows}),
                "metrics": self._metric_summary(rows, baseline if baseline_status == "ACTIVE" else None),
                "groups": self._groups(rows, baseline if baseline_status == "ACTIVE" else None),
            }
            groups_by_checkpoint[checkpoint] = rows
        latest_rows = self._latest_per_post(posts)
        if len(latest_rows) < 3:
            raise ValueError("当前发布样本不足，暂无法形成有效周复盘。至少需要 3 条已有实际指标的发布作品。")
        latest_summary = self._metric_summary(latest_rows, baseline if baseline_status == "ACTIVE" else None)
        checkpoints_used = {checkpoint: sum(1 for row in latest_rows if row.get("selected_checkpoint") == checkpoint)
                            for checkpoint in CHECKPOINT_RANK}
        memory_basis = groups_by_checkpoint["7D"]
        memory_candidates = self._memory_candidates(start.isoformat(), memory_basis,
                                                     baseline if baseline_status == "ACTIVE" else None)
        enough = len(latest_rows) >= 3
        next_week = ([f"继续观察“{item['evidence']['scope_name']}”，目前只有描述性关联；建议再收集一个周期后复核。"
                      for item in memory_candidates]
                     if memory_candidates else (["目前可用的完整 7D 或分组样本不足；先补录真实数据，不建议据此改变已确认策略。"]
                                               if not enough else ["本周可比较样本尚未显示达到记忆建议门槛的稳定分组差异；保持策略并继续积累。"]))
        explanation = self._explain(latest_summary,
                                    self._groups(latest_rows, baseline if baseline_status == "ACTIVE" else None).get("content_pillar", []),
                                    next_week)
        report = {
            "account_id": account_id, "week_start": start.isoformat(), "week_end": end.isoformat(),
            "timezone": "Asia/Shanghai", "published_count": len(posts),
            "metric_coverage": {checkpoint: value["post_count"] for checkpoint, value in checkpoint_summaries.items()},
            "checkpoint_summaries": checkpoint_summaries,
            "latest_available_snapshot": {"post_count": len(latest_rows), "checkpoint_counts": checkpoints_used,
                                          "metrics": latest_summary,
                                          "groups": self._groups(latest_rows, baseline if baseline_status == "ACTIVE" else None)},
            "posts": [{"published_post_id": post["id"], "title": post["title"], "published_at": post["published_at"],
                       "topic_id": post.get("topic_id"), "topic_title": post.get("topic_title"),
                       "pillar_id": post.get("pillar_id"), "pillar_name": post.get("pillar_name"),
                       "content_source": post["content_source"], "hook_type": post.get("hook_type"),
                       "duration_seconds": post.get("duration_seconds"),
                       "checkpoints": [{"checkpoint": metric["checkpoint"], "recorded_at": metric["recorded_at"],
                                        "metrics": {field: metric.get(field) for field in METRIC_FIELDS}}
                                       for metric in post.get("metrics", [])]}
                      for post in posts],
            "baseline": {"id": baseline.get("id"), "version": baseline.get("version"), "status": baseline_status}
                        if baseline else {"id": None, "version": None, "status": "MISSING"},
            "notes": ["只读取人工登记的发布作品和平台数据，不使用历史作品快照冒充本周新发布。",
                      "24小时、72小时、7天数据按节点分别统计；最新可用快照可能由不同节点组成，报告保留各节点覆盖数。",
                      "分组与历史基准的差异仅作描述性比较，不代表因果。"],
            "next_week_suggestions": next_week,
            "explanation": explanation,
            "memory_candidates": memory_candidates,
            "memory_candidate_threshold": {"checkpoint": "7D", "minimum_sample": 3,
                                           "minimum_absolute_baseline_difference": 0.2},
        }
        saved = self.feedback.save_review(account_id, start.isoformat(), end.isoformat(),
                                          baseline.get("id") if baseline_status == "ACTIVE" else None,
                                          baseline.get("version") if baseline_status == "ACTIVE" else None,
                                          self._source_version(posts), report, self._now().isoformat())
        return self.feedback.get_review(account_id, saved["id"]) or saved

    def list_reviews(self, account_id: str) -> list[dict[str, Any]]:
        return self.feedback.list_reviews(account_id)

    def get_review(self, account_id: str, review_id: str) -> dict[str, Any]:
        review = self.feedback.get_review(account_id, review_id)
        if review is None:
            raise ValueError("Weekly Review 不存在或不属于当前账号。")
        return review

    def decide_memory(self, account_id: str, memory_id: str, *, confirm: bool, statement: str | None = None) -> dict[str, Any]:
        current = next((item for item in self.feedback.list_memories(account_id) if item["id"] == memory_id), None)
        if current is None:
            raise ValueError("Strategy Memory 不存在或不属于当前账号。")
        normalized = (statement or current["statement"]).strip()
        if confirm and (not normalized or len(normalized) > 1000):
            raise ValueError("确认的 Memory 不能为空且最多 1000 个字。")
        return self.feedback.decide_memory(account_id, memory_id, confirm=confirm, statement=normalized,
                                           actor="local_user", now=self._now().isoformat())

    def list_memories(self, account_id: str, status: str | None = None) -> list[dict[str, Any]]:
        return self.feedback.list_memories(account_id, status)
