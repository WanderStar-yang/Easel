"""Account-scoped daily topic candidates grounded in an ACTIVE strategy."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from easel.ai_service import AIService, ConfiguredAIService

from .baselines import AccountBaselineService
from .feedback_repository import OperatorFeedbackRepository
from .repository import AccountNotFoundError, OperatorAccountRepository
from .service import OperatorAccountService

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
DOUYIN_WEIGHTS = {
    "strategy_match": 30,
    "historical_support": 25,
    "experiment_value": 20,
    "execution_feasibility": 15,
    "freshness": 10,
}
XHS_WEIGHTS = {
    "positioning_match": 30,
    "audience_value": 25,
    "real_experience": 20,
    "ip_value": 15,
    "feasibility": 10,
}
_TOKEN_CLEANER = re.compile(r"[^\w\u3400-\u9fff]+", re.UNICODE)
_UNSUPPORTED_XHS_CLAIMS = (
    re.compile(r"(?:我|本人).{0,12}(?:从[零0]到[一1]|跑通|重构|踩坑|上线|完成|实现|做过|经历过)", re.IGNORECASE),
    re.compile(r"(?:让我|使我).{0,12}(?:重构|返工|少加|省下|节省|减少|提高|提升).{0,12}(?:次|小时|分钟|天|%|百分比)", re.IGNORECASE),
    re.compile(r"(?:重构|返工|踩坑).{0,8}[0-9一二三四五六七八九十]+次"),
    re.compile(r"每天.{0,8}(?:少加|省下|节省|减少).{0,8}[0-9一二三四五六七八九十]*(?:小时|分钟)"),
)


def _topic_text(value: object) -> str:
    return _TOKEN_CLEANER.sub("", str(value or "").casefold())


def _similarity(left: str, right: str) -> float:
    a, b = _topic_text(left), _topic_text(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) < 4:
        return SequenceMatcher(None, a, b).ratio()
    agrams = {a[i:i + 2] for i in range(len(a) - 1)}
    bgrams = {b[i:i + 2] for i in range(len(b) - 1)}
    overlap = len(agrams & bgrams) / max(1, len(agrams | bgrams))
    return max(overlap, SequenceMatcher(None, a, b).ratio() * 0.8)


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return min(high, max(low, value))


class TopicRecommendationService:
    def __init__(self, repository: OperatorAccountRepository | None = None, *,
                 ai: AIService | None = None, baselines: AccountBaselineService | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.repository.initialize()
        self.accounts = OperatorAccountService(self.repository)
        self.feedback = OperatorFeedbackRepository(self.repository)
        self.baselines = baselines or AccountBaselineService(self.repository)
        self.ai = ai or ConfiguredAIService()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(LOCAL_TIMEZONE)

    def _current_context(self, account_id: str) -> dict[str, Any]:
        account = self.repository.get_account(account_id)
        active = self.repository.get_active_strategy(account_id)
        local_date = self._now().date().isoformat()
        if account["status"] != "ACTIVE" or active is None:
            return {
                "account_id": account_id, "account_name": account["name"],
                "platform": account["platform"], "account_status": account["status"],
                "local_date": local_date, "can_generate": False,
                "gate_reason": "尚未确认运营策略，暂不能生成正式选题。",
                "active_strategy": None, "today": None,
            }

        baseline = self.baselines.latest(account_id)
        diagnosis = self.repository.get_latest_diagnosis(account_id)
        has_history = self.repository.count_posts(account_id) > 0
        if has_history and (baseline is None or baseline.status != "ACTIVE"):
            raise ValueError("历史基准已过期，请先更新历史基准，再生成正式选题。")
        if has_history and (diagnosis is None or diagnosis.get("status") != "CURRENT"):
            raise ValueError("账号诊断已过期，请先重新诊断，再生成正式选题。")

        batch = self.repository.get_daily_topic_batch(account_id, local_date)
        if batch and batch["strategy_id"] != active["id"]:
            batch = None
        return {
            "account_id": account_id, "account_name": account["name"],
            "platform": account["platform"], "account_status": account["status"],
            "local_date": local_date, "can_generate": True, "gate_reason": None,
            "confidence": active["confidence_at_confirmation"],
            "active_strategy": active, "baseline": baseline.as_dict() if baseline else None,
            "diagnosis": diagnosis, "today": batch,
        }

    def today(self, account_id: str) -> dict[str, Any]:
        context = self._current_context(account_id)
        if not context["can_generate"]:
            return {key: context.get(key) for key in (
                "account_id", "account_name", "platform", "account_status", "local_date",
                "can_generate", "gate_reason", "today",
            )}
        active = context["active_strategy"]
        recent = self.repository.list_recent_topics(
            account_id, (date.fromisoformat(context["local_date"]) - timedelta(days=6)).isoformat(), limit=120,
        )
        counts = self._selected_or_recommended_count(recent)
        total = sum(counts.values())
        allocations = [{
            "pillar_id": pillar["id"], "pillar_name": pillar["name"],
            "target_percent": int(pillar.get("allocation_ratio") or 0),
            "recommendations_last_7_days": counts.get(str(pillar["id"]), 0),
            "observed_percent": round(counts.get(str(pillar["id"]), 0) / total * 100, 1) if total else None,
        } for pillar in active.get("pillars", []) if pillar.get("status") == "ACTIVE"]
        return {
            "account_id": context["account_id"], "account_name": context["account_name"],
            "platform": context["platform"], "account_status": context["account_status"],
            "local_date": context["local_date"], "can_generate": True, "gate_reason": None,
            "confidence": active["confidence_at_confirmation"],
            "strategy_id": active["id"], "strategy_version": active["version"],
            "strategy_positioning": active["positioning"],
            "historical_sample_size": (context.get("baseline") or {}).get("sample_size"),
            "baseline_version": (context.get("baseline") or {}).get("version"),
            "allocation_plan": allocations, "today": context.get("today"),
            "generation_mode": (context.get("today") or {}).get("generation_mode"),
        }

    @staticmethod
    def _selected_or_recommended_count(recent: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in recent:
            if item.get("status") in {"SELECTED", "RECOMMENDED"}:
                pillar_id = str(item.get("pillar_id") or "")
                counts[pillar_id] = counts.get(pillar_id, 0) + 1
        return counts

    @classmethod
    def _pillar_order(cls, pillars: list[dict[str, Any]], recent: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Spread each three-topic batch across pillars; favor under-tested pillars for the lead."""
        if not pillars:
            raise ValueError("当前 ACTIVE Strategy 没有可用的 ACTIVE 内容方向。")
        counts = cls._selected_or_recommended_count(recent)
        total = sum(counts.values())

        def deficit(pillar: dict[str, Any]) -> float:
            target = float(pillar.get("allocation_ratio") or 0) / 100
            actual = counts.get(str(pillar["id"]), 0) / total if total else 0
            return target - actual

        return sorted(pillars, key=lambda item: (-deficit(item), str(item["id"])))

    @staticmethod
    def _evidence_for_pillar(pillar: dict[str, Any]) -> list[dict[str, Any]]:
        # This is a snapshot copied from the confirmed recommendation, not model output.
        return [item for item in pillar.get("evidence_summary", []) if isinstance(item, dict)]

    @staticmethod
    def _evidence_digest(pillar: dict[str, Any]) -> dict[str, Any]:
        evidence = TopicRecommendationService._evidence_for_pillar(pillar)
        summaries = []
        for item in evidence:
            difference = item.get("baseline_difference") or {}
            views_delta = (difference.get("views") or {}).get("relative_change")
            er_delta = (difference.get("engagement_rate") or {}).get("relative_change")
            summaries.append({
                "dimension": item.get("dimension"), "group": item.get("group"),
                "sample_size": item.get("sample_size"), "views_median": item.get("views_median"),
                "engagement_rate_median": item.get("engagement_rate_median"),
                "views_relative_to_overall": views_delta,
                "engagement_relative_to_overall": er_delta,
                "evidence_level": item.get("evidence_level"),
            })
        return {"items": summaries, "has_historical_evidence": bool(summaries)}

    @staticmethod
    def _top_low(diagnosis: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
        if not diagnosis or diagnosis.get("status") != "CURRENT":
            return {"top": [], "low": []}
        report = diagnosis.get("report") or {}

        def clean(items: object) -> list[dict[str, Any]]:
            output = []
            for item in (items if isinstance(items, list) else [])[:5]:
                if not isinstance(item, dict):
                    continue
                output.append({key: item.get(key) for key in ("title", "content_type", "views", "engagement_rate")
                               if item.get(key) is not None})
            return output

        return {"top": clean(report.get("top_posts")), "low": clean(report.get("low_posts"))}

    def _prompt(self, account: dict[str, Any], active: dict[str, Any], baseline: dict[str, Any] | None,
                diagnosis: dict[str, Any] | None, pillars: list[dict[str, Any]], recent: list[dict[str, Any]],
                local_date: str, strategy_memory: list[dict[str, Any]] | None = None) -> tuple[str, str]:
        profile = account.get("profile") or {}
        profile_details: dict[str, Any] = {}
        raw_details = profile.get("details_json")
        if isinstance(raw_details, str):
            try:
                parsed_details = json.loads(raw_details)
                profile_details = parsed_details if isinstance(parsed_details, dict) else {}
            except (TypeError, json.JSONDecodeError):
                profile_details = {}
        elif isinstance(profile.get("details"), dict):
            profile_details = profile["details"]
        context = {
            "date": local_date,
            "account_name": account["name"],
            "platform": account["platform"],
            "profile_hypothesis": profile.get("summary") or "",
            "confirmed_positioning": active.get("positioning"),
            "target_audience_hypothesis": active.get("target_audience"),
            "strategy_confidence": active.get("confidence_at_confirmation"),
            "strategy_is_experimental": active.get("confidence_at_confirmation") == "LOW",
            "pillars": [{
                "id": pillar["id"], "name": pillar["name"], "description": pillar["description"],
                "goal": pillar["goal"], "experiment_question": pillar["experiment_question"],
                "allocation_ratio": pillar["allocation_ratio"],
                "historical_evidence": self._evidence_digest(pillar),
            } for pillar in pillars],
            "overall_baseline": ({"sample_size": baseline["sample_size"],
                                  "views_median": (baseline.get("metrics", {}).get("views") or {}).get("median"),
                                  "engagement_rate_median": (baseline.get("metrics", {}).get("engagement_rate") or {}).get("median")}
                                 if baseline else None),
            "historical_top_low": self._top_low(diagnosis),
            "recent_generated_topics_last_7_days": [item.get("title") for item in recent[:30]],
            "strategy_memory": strategy_memory if strategy_memory is not None else profile_details.get("strategy_memory", []),
        }
        system = (
            "你是 Social Operator 的选题创意助手。你只生成创意字段，不打分、不生成历史数字、不修改支柱比例/策略/实验问题。"
            "如提供 strategy_memory，它们是用户确认的描述性观察；只在相关内容方向上用于设计下一次验证，不得写成因果结论、不得改变策略或资源比例；列表为空时不得自行补造经验。"
            "只返回 JSON 对象 {\"topics\":[...]}，严格生成 3 项。每项字段为 pillar_id、title、angle、description、material_requirements。"
            "三项分别使用收到的前三个不同 ACTIVE Pillar ID。标题要具体可执行；description 必须说清拍摄/记录什么、表达什么、为何值得测试。"
            "不得依赖实时热点。不得虚构账号经历、历史表现或已发生事件；设计可拍摄的假设场景时用提问/测试语气。"
            "只能说‘建议测试/观察/验证’，禁止把选题说成会带来、导致或保证播放/互动/完播增长；不要写提高、提升、效果保证等结论。"
            "宠物内容只记录猫自然、舒适的行为；不得制造争抢/惊吓/压力，不得诱导护食或强行佩戴物品。"
            "小红书若只有定位资料、没有具体项目资料，不得虚构第一人称过去经历、具体项目、失败/成功事件、次数、耗时或效率结果；避免‘我是如何…’、‘让我重构三次’等陈述。"
            "小红书标题使用中性问题、方法讨论或待验证假设；说明每个方案须提醒执行者选取本人真实经历，不得捏造项目案例。"
            "材料需求只列轻量拍摄/截图/旁白需求，不建议 AI 视频理解或素材管理。避免近似重复标题。"
        )
        user = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        return system, user

    @staticmethod
    def _parse_ai(text: str, pillars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
        data = json.loads(raw)
        candidates = data.get("topics") if isinstance(data, dict) else data
        if not isinstance(candidates, list) or len(candidates) != 3:
            raise ValueError("模型返回的选题不是 3 项结构化数据。")
        valid_pillars = {str(pillar["id"]) for pillar in pillars}
        normalized = []
        used_pillars: set[str] = set()
        used_titles: set[str] = set()
        for index, item in enumerate(candidates):
            if not isinstance(item, dict):
                raise ValueError("模型选题格式无效。")
            pillar_id = str(item.get("pillar_id") or "")
            if pillar_id not in valid_pillars or pillar_id in used_pillars:
                raise ValueError("模型选题没有按不同 ACTIVE Pillar 生成。")
            title = str(item.get("title") or "").strip()
            angle = str(item.get("angle") or "").strip()
            description = str(item.get("description") or "").strip()
            materials = item.get("material_requirements")
            if isinstance(materials, str):
                materials = [part.strip() for part in re.split(r"[、，,；;\n]+", materials) if part.strip()]
            if not title or not angle or not description or not isinstance(materials, list):
                raise ValueError("模型选题缺少可执行字段。")
            clean_title = _topic_text(title)
            if clean_title in used_titles:
                raise ValueError("模型返回重复选题。")
            used_titles.add(clean_title)
            used_pillars.add(pillar_id)
            normalized.append({
                "pillar_id": pillar_id, "title": title[:120], "angle": angle[:240],
                "description": description[:1200],
                "material_requirements": [str(value).strip()[:120] for value in materials[:8] if str(value).strip()],
                "_slot": index,
            })
        return normalized

    @staticmethod
    def _validate_xhs_candidate(candidate: dict[str, Any]) -> None:
        text = " ".join((candidate.get("title", ""), candidate.get("angle", ""), candidate.get("description", "")))
        if any(pattern.search(text) for pattern in _UNSUPPORTED_XHS_CLAIMS):
            raise ValueError("小红书选题包含未经账号资料支持的个人经历或量化结果。")

    @staticmethod
    def _fallback_candidates(pillars: list[dict[str, Any]], platform: str) -> list[dict[str, Any]]:
        templates = {
            "douyin": [
                ("给缅因留好专属位置后，布偶会不会来“验收”？", "用两个位置做一段双猫空间选择测试",
                 "先拍空位和两只猫分别靠近/停留的瞬间，再用字幕呈现它们的选择；测试观众是否愿意看完这段真实互动。",
                 ["双猫同框", "两个可选位置", "自然反应片段"]),
                ("同一个玩具递给两只猫，谁先发现它在动？", "用同一玩具记录两只猫不同反应",
                 "固定机位拍下玩具出现前后两只猫的反应，用分屏或顺序剪辑呈现差异；验证双猫互动内容的评论与互动表现。",
                 ["双猫同框", "同一个安全玩具", "固定机位"]),
                ("猫咪安静休息时，另一只靠近后会发生什么？", "记录一次不干预的双猫靠近过程",
                 "从两只猫各自休息的镜头开始，连续记录另一只靠近后的真实反应，不摆拍冲突；测试轻松趣味叙事是否能兼顾播放与互动。",
                 ["双猫自然同框", "连续片段", "简短字幕"]),
            ],
            "xiaohongshu": [
                ("一个小功能从需求到能用：我会记录这几步", "用本人真实项目的一次小功能迭代做复盘",
                 "选择你最近实际完成的一项小功能，按需求、关键取舍、遇到的问题、最终验证结果整理图文；发布前用真实项目细节替换，不补造案例。",
                 ["真实功能界面截图", "本人实际开发步骤", "前后变化对照"]),
                ("AI Coding 写出的代码，我会用这 3 步自己验", "记录一次真实的人机协作开发过程",
                 "挑选本人真实用 AI Coding 的一次过程，展示需求输入、人工检查点和最终验证；没有发生的步骤不要写成经历。",
                 ["真实代码或界面截图", "不含密钥的验证过程", "个人复盘旁白"]),
                ("独立开发先做小版本：这个取舍怎么判断？", "用本人真实项目说明一次范围取舍",
                 "选取真实项目中一次删减或延后需求的决定，说明当时约束、取舍和结果；如无对应经历则换成当前正在做的真实决策。",
                 ["真实项目界面", "取舍前后的功能范围", "开发者本人说明"]),
            ],
        }
        source = templates.get(platform, templates["douyin"])
        candidates = []
        for index, pillar in enumerate(pillars[:3]):
            title, angle, description, materials = source[index % len(source)]
            candidates.append({"pillar_id": str(pillar["id"]), "title": title,
                              "angle": angle, "description": description,
                              "material_requirements": materials})
        return candidates

    @staticmethod
    def _historical_score(evidence: list[dict[str, Any]]) -> tuple[int, str]:
        if not evidence:
            return 35, "该方向暂无可用历史分组样本，仅作为假设测试。"
        best = max(evidence, key=lambda item: int(item.get("sample_size") or 0))
        sample = max(0, int(best.get("sample_size") or 0))
        # A descriptive evidence score combines group sample depth with observed median deltas.
        reliability = min(50.0, sample / 20 * 50)
        deltas = []
        difference = best.get("baseline_difference") or {}
        for metric in ("views", "engagement_rate"):
            delta = _number((difference.get(metric) or {}).get("relative_change"))
            if delta is not None:
                deltas.append(_clamp(25 + delta * 25, 0, 50))
        performance = sum(deltas) / len(deltas) if deltas else 25
        score = round(_clamp(reliability + performance))
        phrase = (f"{best.get('group')}样本 {sample} 条，播放中位数 {best.get('views_median', '—')}，"
                  f"互动率中位数 {round(float(best['engagement_rate_median']) * 100, 2) if _number(best.get('engagement_rate_median')) is not None else '—'}%；"
                  "仅作描述性参照。")
        return score, phrase

    @staticmethod
    def _execution(materials: list[str]) -> tuple[int, str, str]:
        count = len(materials)
        complexity = " ".join(materials)
        if count <= 3 and not any(word in complexity for word in ("转场", "特效", "外景", "多机位")):
            return 90, "需求不超过 3 项，常规拍摄/截图即可完成。", "EASY"
        if count <= 6:
            return 72, "需要准备多项素材或简单剪辑。", "MEDIUM"
        return 52, "素材/制作步骤较多，执行成本相对较高。", "HARD"

    @staticmethod
    def _score(platform: str, pillar: dict[str, Any], candidate: dict[str, Any],
               evidence: list[dict[str, Any]], freshness: int) -> tuple[int, dict[str, Any], str]:
        feasibility, feasibility_reason, difficulty = TopicRecommendationService._execution(
            candidate["material_requirements"])
        if platform == "douyin":
            history, history_reason = TopicRecommendationService._historical_score(evidence)
            experiment = 85 if str(pillar.get("experiment_question") or "").strip() else 55
            dimensions = {
                "strategy_match": {"weight": 30, "score": 100, "reason": "关联当前 ACTIVE Content Pillar。"},
                "historical_support": {"weight": 25, "score": history, "reason": history_reason},
                "experiment_value": {"weight": 20, "score": experiment, "reason": str(pillar.get("experiment_question") or "暂无明确实验问题。")},
                "execution_feasibility": {"weight": 15, "score": feasibility, "reason": feasibility_reason},
                "freshness": {"weight": 10, "score": freshness, "reason": f"近 7 天相似度惩罚后得分 {freshness}/100。"},
            }
            reason = f"对应已确认的“{pillar['name']}”方向。历史线索：{history_reason} 当前策略仍处于实验验证期，建议测试而非视为最佳内容。"
            weights = DOUYIN_WEIGHTS
        else:
            # No Xiaohongshu demographic or historical performance assumptions are inferred.
            audience = 75 if any(token in candidate["description"] for token in ("问题", "步骤", "取舍", "验证", "解决")) else 60
            real_experience = 55 if any(token in candidate["description"] for token in ("真实项目", "本人实际", "真实经历")) else 35
            ip_value = 85 if any(token in candidate["title"] + candidate["description"] for token in ("我", "本人", "独立开发者")) else 65
            dimensions = {
                "positioning_match": {"weight": 30, "score": 90, "reason": f"关联已确认定位与“{pillar['name']}”方向。"},
                "audience_value": {"weight": 25, "score": audience, "reason": "按选题是否回应实际开发问题/步骤作规则化评分，不代表用户画像数据。"},
                "real_experience": {"weight": 20, "score": real_experience, "reason": "仅凭现有账号资料没有具体项目经历，执行前需补入本人真实案例。"},
                "ip_value": {"weight": 15, "score": ip_value, "reason": "围绕独立开发者本人决策、过程或复盘建立表达。"},
                "feasibility": {"weight": 10, "score": feasibility, "reason": feasibility_reason},
            }
            reason = f"对应已确认的“{pillar['name']}”方向，作为定位假设驱动的首阶段实验。当前没有可引用的历史基准；执行时需提供真实项目经历，不代表历史数据结论。"
            weights = XHS_WEIGHTS
        total = round(sum(value["weight"] * value["score"] for value in dimensions.values()) / 100)
        breakdown = {
            "platform": platform, "formula_version": "r1-topic-score-v1", "total": total,
            "weights_total": sum(weights.values()),
            "dimensions": {key: {**value, "contribution": round(value["weight"] * value["score"] / 100, 2)}
                           for key, value in dimensions.items()},
            "note": "0–100 的规则化优先级分数，不是成功概率。",
        }
        return total, breakdown, difficulty

    @staticmethod
    def _experiment_question(active: dict[str, Any], pillar: dict[str, Any]) -> str:
        for item in (active.get("experiment_plan") or {}).get("tests", []):
            if item.get("pillar_name") == pillar.get("name") and item.get("question"):
                return str(item["question"])
        return str(pillar.get("experiment_question") or "在后续真实发布数据中继续验证该方向。")

    @staticmethod
    def _allocation_context(recent: list[dict[str, Any]], pillars: list[dict[str, Any]]) -> dict[str, Any]:
        counts = TopicRecommendationService._selected_or_recommended_count(recent)
        used = sum(counts.values())
        return {str(pillar["id"]): {
            "name": pillar["name"], "target_percent": int(pillar.get("allocation_ratio") or 0),
            "recommended_or_selected_last_7_days": counts.get(str(pillar["id"]), 0),
            "allocation_balance_priority": round(float(pillar.get("allocation_ratio") or 0) / 100
                                                  - counts.get(str(pillar["id"]), 0) / used, 3) if used else None,
        } for pillar in pillars}

    def generate(self, account_id: str) -> dict[str, Any]:
        context = self._current_context(account_id)
        if not context["can_generate"]:
            raise ValueError(context["gate_reason"])
        account = self.repository.get_account(account_id)
        active = context["active_strategy"]
        pillars = [pillar for pillar in active.get("pillars", []) if pillar.get("status") == "ACTIVE"]
        if not pillars:
            raise ValueError("当前 ACTIVE Strategy 没有可用的 ACTIVE 内容方向。")
        if len(pillars) < 3:
            raise ValueError("每日 3 选 1 需要至少 3 个 ACTIVE 内容方向。")
        today = date.fromisoformat(context["local_date"])
        since = (today - timedelta(days=6)).isoformat()
        recent = self.repository.list_recent_topics(account_id, since, limit=120)
        ordered = self._pillar_order(pillars, recent)
        active_memories = self.feedback.list_active_strategy_memories(account_id)
        memory_context = [{"statement": item["statement"], "scope": item.get("evidence", {}).get("scope_name"),
                           "scope_key": item.get("evidence", {}).get("scope_key"),
                           "metric": item.get("evidence", {}).get("metric")}
                          for item in active_memories]
        # Generate one candidate per active pillar for a three-pillar strategy.
        assigned = ordered[:3]
        baseline = context.get("baseline")
        diagnosis = context.get("diagnosis")
        mode = "AI"
        try:
            status = self.ai.runtime_status()
            if getattr(getattr(status, "state", None), "value", None) != "AVAILABLE":
                raise RuntimeError("AI runtime unavailable")
            system, user = self._prompt(account, active, baseline, diagnosis, assigned, recent,
                                        context["local_date"], strategy_memory=memory_context)
            candidates = self._parse_ai(self.ai.complete(system, user), assigned)
            if account["platform"] == "xiaohongshu":
                for candidate in candidates:
                    self._validate_xhs_candidate(candidate)
        except Exception:  # noqa: BLE001 - no provider secrets or raw response enter logs/results.
            mode = "TEMPLATE"
            candidates = self._fallback_candidates(assigned, account["platform"])

        by_pillar = {str(pillar["id"]): pillar for pillar in pillars}
        existing_titles = [str(item.get("title") or "") for item in recent]
        prepared: list[dict[str, Any]] = []
        for candidate in candidates:
            pillar = by_pillar[candidate["pillar_id"]]
            evidence = self._evidence_for_pillar(pillar)
            similarity = max((_similarity(candidate["title"], title) for title in existing_titles), default=0.0)
            # Earlier candidates in the same batch also constrain repetition.
            similarity = max(similarity, max((_similarity(candidate["title"], item["title"])
                                              for item in prepared), default=0.0))
            freshness = round(_clamp(100 * (1 - similarity)))
            score, breakdown, difficulty = self._score(account["platform"], pillar, candidate, evidence, freshness)
            pillar_memories = [item for item in memory_context if item.get("scope_key") == pillar["id"]]
            prepared.append({
                **candidate, "score": score, "score_breakdown": breakdown,
                "recommendation_reason": self._recommendation_reason(account, active, pillar, evidence, pillar_memories),
                "historical_evidence": evidence,
                "experiment_question": self._experiment_question(active, pillar),
                "production_difficulty": difficulty,
                "similarity_score": round(similarity, 4),
            })

        # Pick the best score except when scores are close: then respect the rolling seven-day pillar balance.
        highest = max(item["score"] for item in prepared)
        score_window = [item for item in prepared if highest - item["score"] <= 12]
        counts = self._selected_or_recommended_count(recent)
        total = sum(counts.values())
        def balance_priority(item: dict[str, Any]) -> tuple[float, int, str]:
            pillar = by_pillar[item["pillar_id"]]
            deficit = float(pillar.get("allocation_ratio") or 0) / 100 - (
                counts.get(item["pillar_id"], 0) / total if total else 0)
            return deficit, item["score"], item["pillar_id"]
        primary = max(score_window, key=balance_priority)
        generated_at = self._now().isoformat()
        for item in prepared:
            item.update({
                "id": f"topic-{uuid4().hex}", "account_id": account_id,
                "strategy_id": active["id"],
                "status": "RECOMMENDED" if item is primary else "CANDIDATE",
                "created_at": generated_at,
            })
        return self.repository.save_daily_topic_batch(
            account_id, strategy_id=active["id"], batch_id=f"topic-batch-{uuid4().hex}",
            local_date=context["local_date"], generated_at=generated_at,
            generation_mode=mode, topics=prepared,
        )

    @staticmethod
    def _recommendation_reason(account: dict[str, Any], active: dict[str, Any],
                               pillar: dict[str, Any], evidence: list[dict[str, Any]],
                               memories: list[dict[str, Any]] | None = None) -> str:
        memory_note = ""
        if memories:
            summary = str(memories[0].get("statement") or "").strip()
            if summary:
                memory_note = f" 已确认经验：{summary[:240]} 本选题将继续验证该观察，不直接改写当前策略。"
        if account["platform"] == "xiaohongshu":
            return (f"对应已确认定位“{active['positioning']}”与内容方向“{pillar['name']}”。"
                    "当前属于定位假设驱动的第一阶段实验，没有历史表现数据；发布前需补入本人真实项目经历。" + memory_note)
        detail = "该方向尚无可用分组样本。"
        if evidence:
            best = max(evidence, key=lambda item: int(item.get("sample_size") or 0))
            sample = best.get("sample_size", 0)
            views = best.get("views_median")
            engagement = _number(best.get("engagement_rate_median"))
            detail = f"{best.get('group')}历史样本 {sample} 条，播放中位数 {views if views is not None else '暂无'}"
            if engagement is not None:
                detail += f"，互动率中位数 {engagement * 100:.2f}%"
            detail += "；这里只作描述性参照。"
        low = "当前策略置信度 LOW，这条建议用于继续验证，不表示最佳内容。" \
            if active.get("confidence_at_confirmation") == "LOW" else "请结合后续发布数据继续验证。"
        return f"对应已确认的“{pillar['name']}”方向。{detail}{low}{memory_note}"

    def select(self, account_id: str, topic_id: str) -> dict[str, Any]:
        self._current_context(account_id)
        return self.repository.select_daily_topic(
            account_id, topic_id, local_date=self._now().date().isoformat(), occurred_at=self._now().isoformat(),
        )
