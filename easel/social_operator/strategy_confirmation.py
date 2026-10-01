"""User-controlled activation of a Phase 5 strategy recommendation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .repository import AccountNotFoundError, OperatorAccountRepository
from .service import OperatorAccountService
from .strategy_recommendations import StrategyRecommendationService


class StrategyConfirmationService:
    def __init__(self, repository: OperatorAccountRepository | None = None, *,
                 recommendations: StrategyRecommendationService | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.repository.initialize()
        self.accounts = OperatorAccountService(self.repository)
        self.recommendations = recommendations or StrategyRecommendationService(self.repository)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def active(self, account_id: str) -> dict[str, Any] | None:
        self.accounts.get_account(account_id)
        return self.repository.get_active_strategy(account_id)

    @staticmethod
    def _experiment_plan(recommendation: dict[str, Any], pillars: list[dict[str, Any]]) -> dict[str, Any]:
        tests: list[dict[str, str]] = []
        evidence_by_id = {str(item.get("id")): item for item in recommendation.get("evidence", [])}
        recommendation_pillars = {str(pillar.get("id")): pillar
                                  for pillar in recommendation.get("pillars", [])}
        for pillar in pillars:
            source = recommendation_pillars.get(str(pillar.get("recommendation_pillar_id")), pillar)
            groups = [str(evidence_by_id.get(str(evidence_id), {}).get("group") or "")
                      for evidence_id in source.get("evidence_ids", [])]
            pillar_name = str(pillar.get("name", ""))
            if "缅因" in groups:
                question = "缅因相关内容较高的历史播放表现，未来四周能否持续？"
            elif "双猫" in groups or "双猫" in pillar_name:
                question = "双猫互动内容能否在未来四周持续获得高于整体基准的互动率？"
            elif "搞笑/趣味" in groups or "趣味" in pillar_name:
                question = "趣味内容较高播放、偏低互动的现象是否稳定，并观察有数据时的涨粉表现。"
            else:
                question = str(pillar.get("experiment_question") or
                               f"未来四周内，{pillar_name}方向是否能获得可重复的真实反馈？")
            tests.append({"pillar_name": pillar_name, "question": question})
        return {"horizon_weeks": 4, "tests": tests,
                "note": "按方向观察新发布作品相对历史基准的表现；本计划不生成具体选题或发布日程。"}

    def confirm(self, account_id: str, payload: dict[str, Any], *, confirmed_by: str = "local_user") -> dict[str, Any]:
        recommendation = self.recommendations.latest(account_id)
        if recommendation is None or recommendation.get("status") != "CURRENT":
            raise ValueError("请先生成并打开一条当前有效的策略建议。")
        recommendation_body = recommendation["recommendation"]
        supplied_id = payload.get("recommendation_id")
        if supplied_id != recommendation["id"]:
            raise ValueError("策略建议版本已变化，请重新打开最新版本。")

        positioning = str(payload.get("positioning") or "").strip()
        if not positioning or len(positioning) > 240:
            raise ValueError("请填写不超过 240 个字的策略定位。")
        original_pillars = recommendation_body.get("pillars") or []
        supplied_pillars = payload.get("pillars") or []
        expected_ids = {str(item.get("id")) for item in original_pillars}
        received_ids = {str(item.get("recommendation_pillar_id")) for item in supplied_pillars}
        if len(supplied_pillars) != len(original_pillars) or received_ids != expected_ids:
            raise ValueError("确认内容必须保留策略建议中的全部内容方向。")
        if not supplied_pillars:
            raise ValueError("至少需要一个内容方向。")
        ratio_total = sum(int(item.get("allocation_ratio", -1)) for item in supplied_pillars)
        if ratio_total != 100:
            raise ValueError(f"内容方向比例合计为 {ratio_total}%，必须为 100% 才能确认。")

        evidence_by_id = {str(item.get("id")): item for item in recommendation_body.get("evidence", [])}
        original_by_id = {str(item.get("id")): item for item in original_pillars}
        confirmed_pillars: list[dict[str, Any]] = []
        for item in supplied_pillars:
            source = original_by_id[str(item["recommendation_pillar_id"])]
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            ratio = int(item.get("allocation_ratio", -1))
            if not name or len(name) > 80 or not description or len(description) > 600:
                raise ValueError("内容方向名称或说明为空，或超出长度限制。")
            if ratio < 0 or ratio > 100:
                raise ValueError("内容方向比例必须在 0% 到 100% 之间。")
            summaries = []
            for evidence_id in source.get("evidence_ids", []):
                evidence = evidence_by_id.get(str(evidence_id))
                if evidence:
                    summaries.append({
                        "source": evidence.get("source"), "dimension": evidence.get("dimension"),
                        "group": evidence.get("group"), "evidence_level": evidence.get("level"),
                        "sample_size": evidence.get("sample_size"),
                        "views_median": evidence.get("views_median"),
                        "engagement_rate_median": evidence.get("engagement_rate_median"),
                        "baseline_difference": evidence.get("baseline_difference"),
                    })
            confirmed_pillars.append({
                "recommendation_pillar_id": source["id"], "name": name, "description": description,
                "allocation_ratio": ratio, "goal": source.get("goal", "验证该方向的新作品表现。"),
                "experiment_question": source.get("experiment_question", "未来四周表现相对历史基准如何？"),
                "evidence_summary": summaries,
            })

        by_source_order = {str(item["id"]): index for index, item in enumerate(original_pillars)}
        confirmed_pillars.sort(key=lambda item: by_source_order[item["recommendation_pillar_id"]])
        target_audience = str((recommendation_body.get("audience_hypothesis") or {}).get("summary") or "")
        plan = self._experiment_plan(recommendation_body, confirmed_pillars)
        return self.repository.confirm_strategy(
            account_id, recommendation["id"], positioning=positioning,
            target_audience=target_audience, pillars=confirmed_pillars,
            experiment_plan=plan, confidence=recommendation_body["confidence"],
            confirmed_by=confirmed_by, now=self._now(),
        )
