"""Evidence-led, versioned strategy recommendation (Phase 5; never activates strategy)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from easel.ai_service import AIService, ConfiguredAIService

from .baselines import AccountBaselineService
from .canonical import canonical_unique_posts
from .repository import AccountNotFoundError, OperatorAccountRepository
from .service import OperatorAccountService

MIN_DISPLAY_GROUP = 3
MIN_FORMAL_GROUP = 5
_CAUSAL = re.compile(
    r"导致|证明|提升|提高|增强|带来|促进|支撑作用|效果|原因|因果|有效|增长|更多播放|流量|爆款|"
    r"受众认同|情感共鸣|传播度|播放量与分享率|精准用户|粉丝画像"
)


class StrategyRecommendationService:
    def __init__(self, repository: OperatorAccountRepository | None = None, *,
                 ai: AIService | None = None, baselines: AccountBaselineService | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.repository.initialize()
        self.accounts = OperatorAccountService(self.repository)
        self.baselines = baselines or AccountBaselineService(self.repository)
        self.ai = ai or ConfiguredAIService()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _metric(group: dict[str, Any], name: str) -> dict[str, Any]:
        return group.get("metrics", {}).get(name, {})

    def _source(self, account_id: str) -> tuple[dict, dict | None, dict | None, list[dict], str | None]:
        account = self.repository.get_account(account_id)
        diagnosis = self.repository.get_latest_diagnosis(account_id)
        baseline_model = self.baselines.latest(account_id)
        if baseline_model and baseline_model.status != "ACTIVE":
            raise ValueError("历史基准已过期，请先更新历史基准，再生成策略建议。")
        if diagnosis and diagnosis.get("status") == "STALE":
            raise ValueError("账号诊断已过期，请先重新诊断，再生成策略建议。")
        baseline = None
        if baseline_model:
            baseline = {
                "id": baseline_model.id, "version": baseline_model.version,
                "sample_size": baseline_model.sample_size, "period_start": baseline_model.period_start,
                "period_end": baseline_model.period_end, "metrics": baseline_model.metrics,
                "segments": baseline_model.segments,
                "historical_data_version": baseline_model.historical_data_version,
            }
        elif self.repository.list_posts(account_id, limit=1):
            raise ValueError("该账号已有历史作品，但尚未建立有效历史基准。")
        raw = self.repository.list_posts(account_id, limit=100000)
        posts = canonical_unique_posts(raw)
        version = baseline["historical_data_version"] if baseline else self.baselines.current_data_version(account_id)
        return account, diagnosis, baseline, posts, version

    def _evidence(self, account: dict, diagnosis: dict | None, baseline: dict | None) -> list[dict[str, Any]]:
        if not baseline:
            return []
        evidence: list[dict[str, Any]] = []
        overall = baseline.get("metrics", {})
        views = overall.get("views", {})
        engagement = overall.get("engagement_rate", {})
        overall_evidence = {"id": "overall_baseline", "source": "Overall Baseline",
                            "level": "SUPPORTED", "sample_size": baseline["sample_size"],
                            "views_median": views.get("median"),
                            "views_p25": views.get("p25"), "views_p75": views.get("p75"),
                            "engagement_rate_median": engagement.get("median"),
                            "engagement_rate_p25": engagement.get("p25"),
                            "engagement_rate_p75": engagement.get("p75"),
                            "note": "账号整体历史中位数；用于比较参照，不代表目标或因果。"}
        segments = baseline.get("segments", {})
        for dimension in ("subjects", "content_type", "content_source"):
            segment = segments.get(dimension) or {}
            if dimension == "content_source" and (segment.get("coverage") or 0) < 0.7:
                # Sparse source labels must not become a REAL-vs-AI conclusion.
                continue
            for group in segment.get("groups", []):
                sample = int(group.get("sample_size") or 0)
                if sample < MIN_DISPLAY_GROUP or group.get("key") in {"UNKNOWN", "未分类", "[]", ""}:
                    continue
                ev_id = f"{dimension}:{group['key']}"
                views_metric = self._metric(group, "views")
                er_metric = self._metric(group, "engagement_rate")
                evidence.append({"id": ev_id, "source": f"Segment Baseline · {dimension}",
                                 "dimension": dimension, "group": group["key"],
                                 "level": "SUPPORTED" if sample >= MIN_FORMAL_GROUP else "EXPERIMENTAL",
                                 "sample_size": sample,
                                 "eligible_for_formal_comparison": sample >= MIN_FORMAL_GROUP,
                                 "views_median": views_metric.get("median"),
                                 "views_p25": views_metric.get("p25"),
                                 "views_p75": views_metric.get("p75"),
                                 "engagement_rate_median": er_metric.get("median"),
                                 "engagement_rate_p25": er_metric.get("p25"),
                                 "engagement_rate_p75": er_metric.get("p75"),
                                 "overall_views_median": views.get("median"),
                                 "overall_engagement_rate_median": engagement.get("median"),
                                 "baseline_difference": group.get("baseline_difference", {}),
                                 "note": "描述性历史差异，不表示该分类造成表现变化。"})
        top_low_evidence = None
        if diagnosis:
            report = diagnosis.get("report", {})
            quality = report.get("data_quality", {})
            distribution = report.get("content_distribution", {})
            evidence.append({"id": "diagnosis_data_quality", "source": "Diagnosis",
                             "level": "EXPERIMENTAL", "confidence": report.get("confidence"),
                             "sample_size": quality.get("sample_size"),
                             "content_distribution": distribution,
                             "note": "仅作数据质量和分类完整度背景，不从自然语言报告推算指标。"})
            top_posts = report.get("top_posts") or []
            low_posts = report.get("low_posts") or []
            if top_posts or low_posts:
                top_low_evidence = {"id": "diagnosis_top_low", "source": "Diagnosis · Top/Low",
                                    "level": "EXPERIMENTAL", "top_sample_count": len(top_posts),
                                    "low_sample_count": len(low_posts),
                                    "ranking_rule": report.get("ranking_rule"),
                                    "note": "仅作待复核线索；不从标题或排名推断表现原因。"}
        evidence.append(overall_evidence)
        if top_low_evidence:
            evidence.append(top_low_evidence)
        return evidence

    @staticmethod
    def _subject_evidence_sufficiency(baseline: dict | None) -> dict[str, Any]:
        """Conservative sufficiency screen; unknown posts are a real source of bias."""
        segments = (baseline or {}).get("segments", {})
        subjects = segments.get("subjects", {})
        groups = {item.get("key"): int(item.get("sample_size") or 0)
                  for item in subjects.get("groups", [])}
        main_groups = {key: groups.get(key, 0) for key in ("缅因", "布偶", "双猫")}
        unknown_count = max(0, int((baseline or {}).get("sample_size") or 0)
                            - int(subjects.get("classified_sample_count") or 0))
        minimum_main_group = min(main_groups.values()) if main_groups else 0
        coverage = float(subjects.get("coverage") or 0)
        # The bound is deliberately conservative: unresolved posts are not
        # assumed to resemble the already-labelled sample.
        unknown_bias = (unknown_count < minimum_main_group
                        and unknown_count / max(1, int((baseline or {}).get("sample_size") or 0)) <= 0.20)
        groups_sufficient = all(count >= MIN_FORMAL_GROUP for count in main_groups.values())
        coverage_sufficient = coverage >= 0.75
        return {
            "subjects_coverage": coverage,
            "subjects_classified_count": int(subjects.get("classified_sample_count") or 0),
            "unknown_count": unknown_count,
            "major_group_sample_sizes": main_groups,
            "major_groups_sufficient": groups_sufficient,
            "coverage_sufficient": coverage_sufficient,
            "unknown_bias_sufficient": unknown_bias,
            "unknown_could_change_comparison": not unknown_bias,
            "sufficient": coverage_sufficient and groups_sufficient and unknown_bias,
            "note": ("剩余未分类作品较多，主体间比较仍存在较大不确定性。"
                     if not unknown_bias else "主要主体样本和未分类作品比例达到当前比较参考门槛。"),
        }

    @staticmethod
    def _default_pillars(account: dict, evidence: list[dict]) -> list[dict[str, Any]]:
        supported = [item for item in evidence if item.get("source", "").startswith("Segment")
                     and item["level"] == "SUPPORTED"]
        if not supported:
            summary = ((account.get("profile") or {}).get("summary") or "").strip()
            if "开发" in summary or account.get("platform") == "xiaohongshu":
                names = ["真实项目过程", "AI 工具实践", "开发问题复盘", "独立开发记录"]
            else:
                names = ["日常陪伴记录", "猫咪互动观察", "养宠经验记录", "轻松趣味记录"]
            return [{"id": f"p{i+1}", "name": name, "description": "作为起步假设，先通过连续实验收集反馈。",
                     "initial_test_allocation": ratio, "evidence_level": "EXPERIMENTAL",
                     "evidence_ids": [], "goal": "验证受众是否愿意持续观看或互动。",
                     "experiment_question": "连续四周测试后，是否出现可重复的受众反馈？",
                     "why": "暂无历史分组数据，以均衡探索方式收集反馈。",
                     "allocation_reason": {"method": "equal_exploration", "summary": "暂无历史分组数据，按均衡探索分配。"}}
                    for i, (name, ratio) in enumerate(zip(names, (30, 25, 25, 20)))]
        if account.get("platform") == "douyin":
            evidence_by_id = {item["id"]: item for item in evidence}
            themes = [
                ("猫咪日常与陪伴", ("content_type:单猫日常", "content_type:情绪/陪伴",
                                   "subjects:缅因", "subjects:布偶"), 40),
                ("双猫共同生活与互动", ("subjects:双猫", "content_type:双猫互动"), 30),
                ("轻松趣味记录", ("content_type:搞笑/趣味",), 30),
            ]
            pillars = []
            for index, (name, refs, ratio) in enumerate(themes):
                linked = [evidence_by_id[ref] for ref in refs if ref in evidence_by_id]
                supported_links = [item for item in linked if item["level"] == "SUPPORTED"]
                level = "SUPPORTED" if supported_links else "EXPERIMENTAL"
                pillars.append({"id": f"p{index + 1}", "name": name,
                                "description": "以相关历史分组和账号双猫家庭资料作为待验证起点；历史差异仅为描述性观察。",
                                "initial_test_allocation": ratio, "evidence_level": level,
                                "evidence_ids": [item["id"] for item in supported_links],
                                "goal": "检验该内容方向在新增作品中能否持续获得反馈。",
                                "experiment_question": "四周后，该方向的播放和互动相对账号历史基准处于什么范围？",
                                "why": "根据相关历史分组表现、互动、样本量及账号资料形成待验证方向。",
                                "allocation_reason": {"method": "evidence_weighted", "summary": "正在按历史表现、样本量、账号目标和实验价值计算。"}})
            StrategyRecommendationService._allocate_douyin_pillars(pillars, evidence, account)
            return pillars
        # Pillars follow real group dimensions, not a mechanical one-segment-one-pillar map.
        candidates = []
        names = {"缅因": "缅因日常与陪伴", "布偶": "布偶日常与陪伴", "双猫": "双猫相处记录",
                 "单猫日常": "单猫日常记录", "双猫互动": "双猫互动观察", "搞笑/趣味": "轻松趣味记录",
                 "情绪/陪伴": "陪伴感内容"}
        for item in supported:
            if item.get("group") not in names:
                continue
            candidates.append((item, names[item["group"]]))
        candidates = candidates[:3]
        pillars = [{"id": f"p{i+1}", "name": name,
                    "description": "以历史分类样本作为起点，继续观察后续表现。",
                    "initial_test_allocation": ratio, "evidence_level": item["level"],
                    "evidence_ids": [item["id"]], "goal": "检验该方向能否在新增作品中保持稳定反馈。",
                    "experiment_question": "后续作品相对账号历史中位数处于什么范围？",
                    "why": "该分组已有可复核历史样本，仍需在新作品中验证。",
                    "allocation_reason": {"method": "evidence_weighted", "summary": "基于历史表现、样本量和实验需要形成测试分配。"}}
                   for i, (item, name, ratio) in enumerate(
                       (item, name, ratio) for (item, name), ratio in zip(candidates, (30, 25, 25)))]
        if len(pillars) < 3:
            fillers = ["日常陪伴记录", "猫咪互动观察", "轻松趣味记录"]
            for name in fillers:
                if len(pillars) >= 3:
                    break
                if not any(p["name"] == name for p in pillars):
                    pillars.append({"id": f"p{len(pillars)+1}", "name": name,
                                    "description": "当前分类数据不足，作为待验证方向。",
                                    "initial_test_allocation": 20, "evidence_level": "EXPERIMENTAL",
                                    "evidence_ids": [], "goal": "收集可比较的新样本。",
                                    "experiment_question": "该方向是否能获得可重复的受众反馈？",
                                    "why": "目前缺少该方向的历史分组样本，先保留探索空间。",
                                    "allocation_reason": {"method": "equal_exploration", "summary": "分类数据不足，保留探索性测试空间。"}})
        # Normalize ratio deterministically while preserving the total exactly.
        total = sum(p["initial_test_allocation"] for p in pillars)
        pillars[-1]["initial_test_allocation"] += 100 - total
        return pillars

    @staticmethod
    def _allocate_douyin_pillars(pillars: list[dict[str, Any]], evidence: list[dict], account: dict) -> None:
        """Derive understandable test shares from observable inputs, not model output."""
        by_id = {item["id"]: item for item in evidence}
        profile = ((account.get("profile") or {}).get("summary") or "").strip()
        profile_fit = 1.0 if any(word in profile for word in ("猫", "宠物", "双猫")) else 0.8
        scores = []
        for pillar in pillars:
            linked = [by_id[item_id] for item_id in pillar["evidence_ids"] if item_id in by_id]
            views = [item["views_median"] / item["overall_views_median"] for item in linked
                     if isinstance(item.get("views_median"), (int, float))
                     and isinstance(item.get("overall_views_median"), (int, float))
                     and item["overall_views_median"] > 0]
            interactions = [item["engagement_rate_median"] / item["overall_engagement_rate_median"]
                            for item in linked if isinstance(item.get("engagement_rate_median"), (int, float))
                            and isinstance(item.get("overall_engagement_rate_median"), (int, float))
                            and item["overall_engagement_rate_median"] > 0]
            views_index = sum(views) / len(views) if views else 1.0
            engagement_index = sum(interactions) / len(interactions) if interactions else 1.0
            sample_size = max((int(item.get("sample_size") or 0) for item in linked), default=0)
            reliability = min(sample_size / 10, 1.0)
            experiment_value = 1.2 if sample_size < MIN_FORMAL_GROUP else 1.0
            score = (0.30 * min(1.5, max(0.5, views_index))
                     + 0.20 * min(1.5, max(0.5, engagement_index))
                     + 0.20 * reliability + 0.15 * profile_fit + 0.15 * experiment_value)
            scores.append(score)
            direction = "高于" if views_index > 1.02 else "低于" if views_index < 0.98 else "接近"
            subject_group = next((item for item in linked if item.get("dimension") == "subjects"), None)
            focus_group = subject_group or (linked[0] if linked else None)
            if focus_group:
                views_text = (f"播放中位数 {focus_group['views_median']:g}，{direction}整体"
                              if isinstance(focus_group.get("views_median"), (int, float)) else "播放数据不足")
                engagement = focus_group.get("engagement_rate_median")
                overall_engagement = focus_group.get("overall_engagement_rate_median")
                engagement_text = (f"互动率中位数 {engagement:.2%}，"
                                   f"{'高于' if engagement > overall_engagement else '低于' if engagement < overall_engagement else '接近'}整体"
                                   if isinstance(engagement, (int, float)) and isinstance(overall_engagement, (int, float))
                                   else "互动率数据不足")
                dimension_label = "出镜主体" if focus_group.get("dimension") == "subjects" else "内容类型"
                special_reason = ("双猫是账号既有 IP 关系线索；" if focus_group.get("group") == "双猫" else "")
                focus_sample = focus_group.get("sample_size") or sample_size
                pillar["why"] = (f"{special_reason}{dimension_label}{focus_group.get('group')}样本 {focus_sample} 条，{views_text}；{engagement_text}。"
                                 "因此保留相应测试资源，用后续作品验证能否重复出现，不把历史差异解释为因果。")
            else:
                pillar["why"] = "目前缺少可比较的历史分组，保留该方向用于均衡收集样本。"
            pillar["allocation_reason"] = {
                "method": "evidence_weighted",
                "summary": (f"按历史播放指数（30%）、互动率指数（20%）、样本可靠度（20%）、账号目标匹配（15%）和探索价值（15%）计分；"
                            f"支持分组最多样本 {sample_size} 条。比例用于测试资源分配。"),
                "views_index": round(views_index, 4), "engagement_index": round(engagement_index, 4),
                "sample_size": sample_size, "sample_reliability": round(reliability, 4),
                "account_goal_fit": profile_fit, "experiment_value": experiment_value,
                "score": round(score, 4), "evidence_ids": [item["id"] for item in linked],
            }
        total = sum(scores)
        allocations = [round(score / total * 100) for score in scores] if total else [34, 33, 33]
        allocations[-1] += 100 - sum(allocations)
        for pillar, allocation in zip(pillars, allocations):
            pillar["initial_test_allocation"] = allocation

    def _llm_copy(self, pillars: list[dict[str, Any]], profile: str) -> tuple[list[dict[str, Any]], str]:
        try:
            prompt = {"account_profile_hypothesis": profile,
                      "pillars": [{"id": p["id"], "name": p["name"],
                                   "evidence_level": p["evidence_level"], "evidence_ids": p["evidence_ids"]}
                                  for p in pillars]}
            answer = self.ai.complete(
                "你是策略建议的文字整理助手。只可把输入支柱名称润色为简短显示名称，保留原有含义。"
                "不得添加新主题、证据、数值、受众人口属性或因果结论；不得建议选题、日历、发布计划或生成内容。"
                "返回 JSON：{pillars:[{id,name}]}。",
                json.dumps(prompt, ensure_ascii=False),
            )
            parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip(), flags=re.I))
            by_id = {p["id"]: p for p in parsed.get("pillars", []) if isinstance(p, dict)}
            result = []
            for pillar in pillars:
                candidate = by_id.get(pillar["id"], {})
                updated = dict(pillar)
                # Only a short display name is eligible for model wording. All
                # substantive copy remains deterministic, so the model cannot
                # turn correlation into a claim or add actions/metrics.
                value = candidate.get("name")
                if (isinstance(value, str) and 1 <= len(value.strip()) <= 16
                        and not _CAUSAL.search(value)):
                    updated["name"] = value.strip()
                result.append(updated)
            return result, "available"
        except Exception:  # LLM is an optional copy editor; deterministic recommendation remains usable.
            return pillars, "fallback"

    def generate(self, account_id: str) -> dict[str, Any]:
        account, diagnosis, baseline, posts, data_version = self._source(account_id)
        evidence = self._evidence(account, diagnosis, baseline)
        pillars = self._default_pillars(account, evidence)
        profile = ((account.get("profile") or {}).get("summary") or "").strip()
        pillars, language_refinement = self._llm_copy(pillars, profile)
        positioning = profile or ("围绕真实项目与开发过程建立内容定位假设。"
                                  if account["platform"] == "xiaohongshu" else "围绕宠物日常与陪伴建立内容定位假设。")
        audience = ("对独立开发、AI 工具和真实项目过程感兴趣的读者（待验证的兴趣假设）。"
                    if account["platform"] == "xiaohongshu" else
                    "对猫咪日常、双猫相处和养宠经验感兴趣的观众（待验证的兴趣假设）。")
        segment_evidence = [item for item in evidence if item.get("source", "").startswith("Segment")]
        problem_observations = []
        if baseline:
            for dimension in ("content_source", "content_type", "subjects"):
                coverage = ((baseline.get("segments") or {}).get(dimension) or {}).get("coverage")
                if isinstance(coverage, (int, float)) and coverage < 0.7:
                    problem_observations.append(
                        f"{ {'content_source': '内容来源', 'content_type': '内容类型', 'subjects': '出镜主体'}[dimension] }分类覆盖为 {coverage:.0%}，相关分组证据有限。"
                    )
        opportunity_directions = [
            {"evidence_id": item["id"], "group": item.get("group"), "dimension": item.get("dimension"),
             "evidence_level": item["level"], "sample_size": item["sample_size"]}
            for item in segment_evidence
        ]
        confidence = "LOW"
        evidence_sufficiency = self._subject_evidence_sufficiency(baseline)
        if baseline and diagnosis and diagnosis.get("status") == "CURRENT":
            quality = diagnosis.get("report", {}).get("confidence")
            source = (baseline.get("segments") or {}).get("content_source", {})
            source_coverage = source.get("coverage", 0) or 0
            segment_data = baseline.get("segments") or {}
            type_coverage = (segment_data.get("content_type") or {}).get("coverage", 0) or 0
            formal_groups = sum(
                int(group.get("sample_size") or 0) >= MIN_FORMAL_GROUP
                for dimension in ("subjects", "content_type")
                for group in (segment_data.get(dimension) or {}).get("groups", [])
            )
            if (quality == "HIGH" and evidence_sufficiency["sufficient"]
                    and evidence_sufficiency["subjects_coverage"] >= 0.85
                    and type_coverage >= 0.85 and formal_groups >= 3
                    and all(count >= 8 for count in evidence_sufficiency["major_group_sample_sizes"].values())):
                confidence = "HIGH"
            elif quality != "LOW" and evidence_sufficiency["sufficient"] and type_coverage >= 0.70 and formal_groups >= 2:
                confidence = "MEDIUM"
        if not baseline:
            confidence_note = "该账号没有历史作品或历史基准，所有方向仅是低置信度起步假设。"
        elif confidence != "LOW":
            confidence_note = "建议仅用于后续实验，不能解释为因果结论。"
        elif not evidence_sufficiency["unknown_bias_sufficient"]:
            confidence_note = "历史主体或内容类型分类覆盖有限，整体建议保持低置信度；内容来源分类不用于 REAL/AI 结论。"
        else:
            confidence_note = "历史主体分组样本或分类覆盖尚不足，整体建议保持低置信度；内容来源分类不用于 REAL/AI 结论。"
        recommendation = {
            "status": "RECOMMENDED", "activation_status": "NOT_ACTIVATED",
            "account_name": account["name"], "platform": account["platform"],
            "confidence": confidence, "evidence_sufficiency": evidence_sufficiency,
            "confidence_note": confidence_note,
            "evidence": evidence,
            "language_refinement": language_refinement,
            "positioning_hypothesis": {"summary": positioning, "evidence_level": "EXPERIMENTAL",
                                       "note": "沿用账号初始资料作为待验证假设，不代表历史数据已经证实。"},
            "audience_hypothesis": {"summary": audience, "evidence_level": "EXPERIMENTAL",
                                    "demographic_claims": [],
                                    "note": "仅描述内容兴趣方向；当前没有受众人口统计数据。"},
            "problem_observations": problem_observations,
            "opportunity_directions": opportunity_directions,
            "pillars": pillars,
            "experiment_horizon_weeks": 4,
            "experiment_note": "这是初始测试资源分配，不是发布比例要求；每轮结束后依据真实表现复核。",
            "limitations": ([
                "历史分组差异是描述性观察，不能据此推断因果。",
                "样本少于 5 的分组仅作初步参考；少于 3 的分组不展示。",
                "内容来源等分类覆盖较低，相关建议仍需实验验证。",
            ] if baseline else [
                "当前没有历史作品和基准，以下全部为待验证的起步假设。",
                "受众兴趣是假设，目前没有受众数据或人口统计结论。",
            ]),
            "source": {"baseline_id": baseline["id"] if baseline else None,
                       "baseline_version": baseline["version"] if baseline else None,
                       "diagnosis_id": diagnosis["id"] if diagnosis else None,
                       "historical_data_version": data_version,
                       "profile_summary": profile,
                       "canonical_sample_size": len(posts)},
        }
        return self.repository.save_strategy_recommendation(
            str(uuid4()), account_id, baseline_id=baseline["id"] if baseline else None,
            baseline_version=baseline["version"] if baseline else None,
            diagnosis_id=diagnosis["id"] if diagnosis else None,
            generated_at=self._now(), evidence_data_version=data_version, recommendation=recommendation,
        )

    def latest(self, account_id: str) -> dict[str, Any] | None:
        self.accounts.get_account(account_id)
        row = self.repository.get_latest_strategy_recommendation(account_id)
        if not row or row["status"] != "CURRENT":
            return row
        baseline = self.baselines.latest(account_id)
        diagnosis = self.repository.get_latest_diagnosis(account_id)
        account = self.repository.get_account(account_id)
        profile = ((account.get("profile") or {}).get("summary") or "").strip()
        current_data_version = self.baselines.current_data_version(account_id)
        if row["baseline_id"] != (baseline.id if baseline else None) or \
                (baseline is not None and baseline.status != "ACTIVE") or \
                row["diagnosis_id"] != (diagnosis.get("id") if diagnosis else None) or \
                (diagnosis and diagnosis.get("status") == "STALE") or \
                row["evidence_data_version"] != current_data_version or \
                row["recommendation"].get("source", {}).get("profile_summary") != profile:
            self.repository.mark_strategy_recommendation_stale(row["id"])
            row = self.repository.get_latest_strategy_recommendation(account_id)
        return row

    def history(self, account_id: str) -> list[dict[str, Any]]:
        self.accounts.get_account(account_id)
        return self.repository.list_strategy_recommendations(account_id)
