"""Versioned, account-scoped content drafts from explicitly selected Topics."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from easel.ai_service import AIService, AIRuntimeState, AIServiceError, ConfiguredAIService

from .repository import AccountNotFoundError, OperatorAccountRepository

_XHS_UNSUPPORTED_EXPERIENCE = re.compile(
    r"(?:我|本人).{0,18}(?:从[零0]到[一1]|跑通|重构|踩坑|上线|完成|实现|做过|经历过|节省|提高|提升|减少|曾经|之前|当时)",
    re.IGNORECASE,
)
_UNSUPPORTED_MEASURED_CLAIM = re.compile(
    r"(?<!\[)(?:\d+(?:\.\d+)?|[一二三四五六七八九十]+)\s*(?:小时|分钟|天|周|个月|个用户|位客户|元|万元|%|百分比)"
)
_GUARANTEED_RESULTS = re.compile(r"保证(?:涨粉|爆款|增长|提升)|一定(?:爆|涨粉)|必然(?:增长|提升)|百分百爆款")
_UNSAFE_PET_STAGING = re.compile(
    r"(?:纸箱|箱子).{0,18}(?:明显小于|明显偏小|撑得变形|被撑变形)|"
    r"(?:挤进|挤入|塞进|钻进).{0,14}(?:小纸箱|小箱子|明显偏小.{0,3}(?:纸箱|箱子)|明显小于.{0,8}(?:纸箱|箱子))|"
    r"(?:让|诱导|引导).{0,12}(?:卡住|挤进|塞进|困在)"
)

DOUYIN_FIELDS = {
    "content_theme", "recommendation_reason", "content_goal", "hook", "opening_3_seconds",
    "video_structure", "shot_suggestions", "subtitles", "suggested_duration_seconds",
    "title_candidates", "bgm_type", "hashtags", "comment_interaction",
    "posting_time_suggestion", "existing_materials_to_verify", "experiment_tag",
}
XHS_FIELDS = {
    "title_candidates", "cover_text", "opening_hook", "content_structure", "body_markdown",
    "image_structure", "screenshot_suggestions", "project_materials", "cta",
    "comment_interaction", "recommended_topics", "posting_time_suggestion", "experiment_tag",
}
_ARRAY_FIELDS = {
    "title_candidates", "shot_suggestions", "subtitles", "hashtags", "existing_materials_to_verify",
    "content_structure", "image_structure", "screenshot_suggestions", "project_materials", "recommended_topics",
}
_TEXT_LIMITS = {
    "content_theme": 300, "recommendation_reason": 600, "content_goal": 500, "hook": 500,
    "opening_3_seconds": 600, "bgm_type": 160, "comment_interaction": 500,
    "posting_time_suggestion": 200, "experiment_tag": 180, "cover_text": 160,
    "opening_hook": 600, "body_markdown": 12000, "cta": 300,
}


class ContentGenerationService:
    def __init__(self, repository: OperatorAccountRepository | None = None, *,
                 ai: AIService | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.repository.initialize()
        self.ai = ai or ConfiguredAIService()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _fields(platform: str) -> set[str]:
        if platform == "douyin":
            return DOUYIN_FIELDS
        if platform == "xiaohongshu":
            return XHS_FIELDS
        raise ValueError("暂不支持该平台的内容生成。")

    @staticmethod
    def _prompts(context: dict[str, Any]) -> tuple[str, str]:
        platform = context["account"]["platform"]
        if platform == "douyin":
            schema = {
                "content_theme": "string", "recommendation_reason": "string", "content_goal": "string",
                "hook": "string", "opening_3_seconds": "string",
                "video_structure": [{"time_range": "string", "visual": "string", "narration": "string", "subtitle": "string"}],
                "shot_suggestions": ["string"], "subtitles": ["string"],
                "suggested_duration_seconds": "integer", "title_candidates": ["string"],
                "bgm_type": "string", "hashtags": ["string"], "comment_interaction": "string",
                "posting_time_suggestion": "string", "existing_materials_to_verify": ["string"],
                "experiment_tag": "string",
            }
            system = (
                "你是 Easel 抖音宠物账号的短视频内容草稿助手。只为用户已选择的选题写一个可编辑草稿。"
                "严格只返回 JSON 对象，字段和类型必须与提供的 schema 完全一致，不要 Markdown 代码围栏或额外文字。"
                "不要改写选题绑定的策略方向和实验问题，不生成历史播放数据、虚构猫咪行为、虚构现有素材或个人经历。"
                "所有猫咪行为必须自然、安全、可中止；不得制造惊吓、争抢、压力、护食或强迫互动。"
                "不得为了拍摄故意设置不合尺寸或不安全的道具、诱导宠物挤入或卡住、限制行动或堵住出口；只观察宠物自愿互动，"
                "它不参与时就停止该镜头。不能把尚未拍摄的行为写成已发生的事实，镜头用条件式或明确标记为建议演示。"
                "用户选题仅是待验证的主题，不代表相关行为已经发生或应被诱导。纸箱主题只可建议检查已有的自然素材，"
                "或使用尺寸合适、无损坏且出口畅通的纸箱观察宠物是否自愿靠近；不要安排宠物挤进小箱、箱体变形或卡住。"
                "不承诺播放、涨粉或互动结果，不写保证爆款、必然提升等断言。镜头和口播需能由用户自行拍摄/核实。"
                "existing_materials_to_verify 只能列出建议用户检查是否已有的素材，不能声称其已经存在。"
                "将内容主题、推荐理由、内容目标、Hook、前3秒设计、视频结构、镜头建议、字幕、建议时长、"
                "恰好5个标题候选、BGM类型、话题、评论互动、发布时间建议、待核实素材和实验标签都填完整。"
            )
        else:
            schema = {
                "title_candidates": ["string x 5"], "cover_text": "string", "opening_hook": "string",
                "content_structure": ["string"], "body_markdown": "string",
                "image_structure": ["string"], "screenshot_suggestions": ["string"],
                "project_materials": ["string"], "cta": "string", "comment_interaction": "string",
                "recommended_topics": ["string"], "posting_time_suggestion": "string", "experiment_tag": "string",
            }
            system = (
                "你是 Easel 小红书独立开发者账号的图文草稿助手。只为用户已选择的选题写一个可编辑草稿。"
                "严格只返回 JSON 对象，字段和类型必须与提供的 schema 完全一致，不要 Markdown 代码围栏或额外文字。"
                "标题候选必须恰好 5 个。不要虚构账号本人做过的项目、成功/失败、客户、收入、数据、耗时或效率结果。"
                "缺少真实项目细节时，用清楚的方括号占位符提醒用户补入真实材料，或写成方法讨论/待验证假设；"
                "禁止编造第一人称过往经历。不要声称用户已经拥有任何截图或项目素材。"
                "不得保证流量、涨粉或爆款。草稿需包含封面文字、开头 Hook、结构、完整正文、配图结构、截图建议、"
                "项目素材清单、CTA、评论问题、推荐话题、发布时间建议和实验标签。中文自然、具体，供用户审核修改后自行发布。"
            )
        user = json.dumps({"schema": schema, "account": context["account"],
                           "active_strategy": {
                               "version": context["strategy"]["version"],
                               "positioning": context["strategy"]["positioning"],
                               "target_audience": context["strategy"]["target_audience"],
                               "confidence": context["strategy"]["confidence_at_confirmation"],
                           },
                           "selected_topic": {
                               "title": context["topic"]["title"], "angle": context["topic"]["angle"],
                               "description": context["topic"]["description"],
                               "pillar": context["topic"]["pillar_name"],
                               "pillar_description": context["topic"]["pillar_description"],
                               "pillar_goal": context["topic"]["pillar_goal"],
                               "experiment_question": context["topic"]["experiment_question"],
                               "material_requirements": context["topic"]["material_requirements"],
                           }}, ensure_ascii=False, separators=(",", ":"))
        return system, user

    @classmethod
    def _normalize(cls, text: str, platform: str, *, enforce_claim_guards: bool = True) -> dict[str, Any]:
        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("模型返回格式无法识别，请重试。") from exc
        if not isinstance(data, dict) or set(data) != cls._fields(platform):
            raise ValueError("模型未按平台内容模板返回完整字段，请重试。")
        normalized: dict[str, Any] = {}
        for key, value in data.items():
            if key in _ARRAY_FIELDS:
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    raise ValueError(f"草稿字段 {key} 格式无效。")
                if key == "title_candidates" and len(value) != 5:
                    raise ValueError("草稿必须包含 5 个标题候选。")
                normalized[key] = [item.strip()[:500] for item in value[:30] if item.strip()]
                if not normalized[key]:
                    raise ValueError(f"草稿字段 {key} 不能为空。")
            elif key == "video_structure":
                if not isinstance(value, list) or not value or len(value) > 12:
                    raise ValueError("视频结构格式无效。")
                segments = []
                for segment in value:
                    if not isinstance(segment, dict) or set(segment) != {"time_range", "visual", "narration", "subtitle"}:
                        raise ValueError("视频结构的镜头字段不完整。")
                    if any(not isinstance(segment[field], str) or not segment[field].strip()
                           for field in ("time_range", "visual", "narration", "subtitle")):
                        raise ValueError("视频结构字段不能为空。")
                    segments.append({field: segment[field].strip()[:500] for field in segment})
                normalized[key] = segments
            elif key == "suggested_duration_seconds":
                if isinstance(value, bool) or not isinstance(value, int) or not 10 <= value <= 600:
                    raise ValueError("建议时长必须是 10 至 600 秒的整数。")
                normalized[key] = value
            else:
                if key == "comment_interaction" and isinstance(value, str) and not value.strip():
                    # This is a non-factual prompt for the reader, so a neutral default is
                    # safer than discarding an otherwise complete draft from a compatible model.
                    value = "你最想先尝试哪一点？欢迎在评论区分享。"
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"草稿字段 {key} 不能为空。")
                normalized[key] = value.strip()[:_TEXT_LIMITS.get(key, 1000)]
        all_text = json.dumps(normalized, ensure_ascii=False)
        if enforce_claim_guards and _GUARANTEED_RESULTS.search(all_text):
            raise ValueError("草稿含有结果保证性表述，请重试或手动修改。")
        if enforce_claim_guards and platform == "douyin" and _UNSAFE_PET_STAGING.search(all_text):
            raise ValueError("草稿建议了不安全的宠物拍摄方式，请重试或手动修改。")
        if enforce_claim_guards and platform == "xiaohongshu" and _XHS_UNSUPPORTED_EXPERIENCE.search(all_text):
            raise ValueError("草稿包含未经账号资料支持的个人经历，请重试或补入真实信息。")
        if enforce_claim_guards and platform == "xiaohongshu" and _UNSUPPORTED_MEASURED_CLAIM.search(all_text):
            raise ValueError("草稿包含未经账号资料支持的具体数据，请重试或补入真实信息。")
        return normalized

    def get(self, account_id: str, topic_id: str) -> dict[str, Any]:
        context = self.repository.get_selected_topic_for_draft(account_id, topic_id)
        return {**context, "draft": self.repository.get_content_draft(account_id, topic_id)}

    def generate(self, account_id: str, topic_id: str) -> dict[str, Any]:
        context = self.repository.get_selected_topic_for_draft(account_id, topic_id)
        status = self.ai.runtime_status()
        if status.state != AIRuntimeState.AVAILABLE:
            raise RuntimeError({
                AIRuntimeState.NOT_CONFIGURED: "尚未配置可用的 AI 模型，请先完成模型设置。",
                AIRuntimeState.UNAVAILABLE: "AI 服务暂时不可用，请稍后重试。",
                AIRuntimeState.ERROR: "AI 模型配置或请求出错，请检查模型设置后重试。",
            }.get(status.state, "AI 服务暂时不可用。"))
        system, user = self._prompts(context)
        try:
            content = self._normalize(self.ai.complete(system, user), context["account"]["platform"])
        except AIServiceError as exc:
            if exc.state == AIRuntimeState.NOT_CONFIGURED:
                raise RuntimeError("尚未配置可用的 AI 模型，请先完成模型设置。") from None
            if exc.state == AIRuntimeState.UNAVAILABLE:
                raise RuntimeError("AI 模型暂时没有响应或请求超时，请检查网络后重试。") from None
            raise RuntimeError("AI 模型请求失败，请检查模型配置后重试。") from None
        except ValueError as first_error:
            # Compatible models sometimes miss one structural constraint on the first pass.
            # Give them one bounded repair attempt; never persist a partial or invalid draft.
            repair = (
                f"上一次返回未通过格式校验：{first_error}。请重新生成完整 JSON 对象，严格满足原 schema；"
                "不要省略字段，所有数组都满足要求，不要在 JSON 外添加说明。"
            )
            repair_payload = json.loads(user)
            repair_payload["repair_instruction"] = repair
            try:
                repaired = self.ai.complete(system, json.dumps(repair_payload, ensure_ascii=False, separators=(",", ":")))
            except AIServiceError as exc:
                if exc.state == AIRuntimeState.UNAVAILABLE:
                    raise RuntimeError("AI 模型暂时没有响应或请求超时，请检查网络后重试。") from None
                raise RuntimeError("AI 模型请求失败，请检查模型配置后重试。") from None
            content = self._normalize(repaired, context["account"]["platform"])
        draft = self.repository.save_content_draft(
            account_id, topic_id, draft_id=f"content-draft-{uuid4().hex}",
            strategy_id=context["strategy"]["id"], strategy_version=context["strategy"]["version"],
            platform=context["account"]["platform"], content=content, occurred_at=self._now(),
        )
        return {**context, "draft": draft, "provider": status.provider}

    def update(self, account_id: str, topic_id: str, content: dict[str, Any]) -> dict[str, Any]:
        context = self.repository.get_selected_topic_for_draft(account_id, topic_id)
        normalized = self._normalize(json.dumps(content, ensure_ascii=False), context["account"]["platform"],
                                     enforce_claim_guards=False)
        draft = self.repository.update_content_draft(account_id, topic_id, normalized, occurred_at=self._now())
        return {**context, "draft": draft}
