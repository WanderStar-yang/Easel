from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from easel.social_operator.baselines import AccountBaselineService
from easel.social_operator.diagnosis import AccountDiagnosisService
from easel.social_operator.historical import HistoricalPostService
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from easel.social_operator.strategy_recommendations import StrategyRecommendationService
from fastapi.testclient import TestClient
from web.app import app
from web.routers.operator_strategy_recommendations import get_strategy_recommendation_service


class NoAI:
    def runtime_status(self):
        raise AssertionError("recommendation generation should not require a separate runtime probe")

    def complete(self, system_prompt, user_prompt):
        raise RuntimeError("AI unavailable")


class UnsafeCopyAI(NoAI):
    def complete(self, system_prompt, user_prompt):
        import json
        source = json.loads(user_prompt)
        return json.dumps({"pillars": [{"id": p["id"], "name": "该内容导致增长",
                                         "description": "因果保证", "goal": "增长", "experiment_question": "验证？"}
                            for p in source["pillars"]]}, ensure_ascii=False)


def build(tmp_path, count=8):
    repository = OperatorAccountRepository(tmp_path / "strategy.sqlite3")
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    start = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    for index in range(count):
        posts.create_post("douyin-pet", {
            "title": f"作品 {index}", "publish_time": (start + timedelta(days=index)).isoformat(),
            "content_type": "搞笑/趣味" if index < count - 3 else "双猫互动",
            "content_source": "AI" if index == 0 else "UNKNOWN",
            "subjects": ["缅因"] if index < count - 3 else ["双猫"],
            "views": [100, 200, 300, 400, 500, 600, 700, 693000][index % 8],
            "likes": 4, "comments": 1, "favorites": None, "shares": 1,
        })
    diagnosis = AccountDiagnosisService(repository)
    diagnosis.diagnose("douyin-pet")
    baseline_service = AccountBaselineService(repository)
    baseline_service.generate("douyin-pet")
    return repository, accounts, posts, baseline_service


def test_recommendation_uses_segment_thresholds_and_no_causal_claims(tmp_path):
    repository, accounts, _, baseline_service = build(tmp_path, 8)
    strategy = StrategyRecommendationService(repository, ai=UnsafeCopyAI(), baselines=baseline_service)
    result = strategy.generate("douyin-pet")
    body = result["recommendation"]
    assert body["source"]["canonical_sample_size"] == 8
    assert body["source"]["baseline_version"] == 1
    assert body["confidence"] == "LOW"
    assert body["evidence_sufficiency"]["major_group_sample_sizes"] == {"缅因": 5, "布偶": 0, "双猫": 3}
    assert not body["evidence_sufficiency"]["major_groups_sufficient"]
    assert sum(p["initial_test_allocation"] for p in body["pillars"]) == 100
    assert all(p["evidence_level"] != "SUPPORTED" or p["evidence_ids"] for p in body["pillars"])
    assert all(p["why"] and p["allocation_reason"]["method"] == "evidence_weighted"
               for p in body["pillars"])
    assert all("样本" in p["why"] and "播放中位数" in p["why"] for p in body["pillars"]
               if p["evidence_ids"])
    assert all(p["allocation_reason"]["score"] > 0 for p in body["pillars"])
    assert all("导致" not in p["name"] and "因果" not in p["description"] for p in body["pillars"])
    groups = {e["id"]: e for e in body["evidence"]}
    assert groups["overall_baseline"]["views_median"] == 450
    evidence_ids = [e["id"] for e in body["evidence"]]
    assert evidence_ids.index("subjects:缅因") < evidence_ids.index("diagnosis_data_quality")
    assert evidence_ids.index("diagnosis_data_quality") < evidence_ids.index("overall_baseline")
    if "diagnosis_top_low" in evidence_ids:
        assert evidence_ids.index("overall_baseline") < evidence_ids.index("diagnosis_top_low")
    assert groups["subjects:缅因"]["sample_size"] == 5
    assert groups["subjects:缅因"]["level"] == "SUPPORTED"
    assert groups["subjects:缅因"]["baseline_difference"]["views"]["relative_change"] is not None
    assert groups["subjects:双猫"]["sample_size"] == 3
    assert groups["subjects:双猫"]["level"] == "EXPERIMENTAL"
    assert not any(e.get("group") == "AI" for e in body["evidence"])
    assert strategy.latest("douyin-pet")["status"] == "CURRENT"
    assert strategy.latest("xhs-developer") is None
    assert accounts.get_account("douyin-pet").strategy.state == "hypothesis"


def test_no_history_all_pillars_are_low_confidence_hypotheses_and_account_scoped(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "empty.sqlite3")
    OperatorAccountService(repository)
    strategy = StrategyRecommendationService(repository, ai=NoAI())
    result = strategy.generate("xhs-developer")
    body = result["recommendation"]
    assert body["confidence"] == "LOW"
    assert body["source"]["baseline_version"] is None
    assert body["source"]["diagnosis_id"] is None
    assert body["audience_hypothesis"]["demographic_claims"] == []
    assert body["language_refinement"] == "fallback"
    assert result["evidence_data_version"]
    assert strategy.latest("xhs-developer")["status"] == "CURRENT"
    assert all(p["evidence_level"] == "EXPERIMENTAL" for p in body["pillars"])
    assert all(not p["evidence_ids"] for p in body["pillars"])
    assert sum(p["initial_test_allocation"] for p in body["pillars"]) == 100
    assert strategy.latest("douyin-pet") is None
    assert strategy.history("xhs-developer")[0]["account_id"] == "xhs-developer"


def test_new_history_stales_profile_only_recommendation(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "no-history.sqlite3")
    OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    strategy = StrategyRecommendationService(repository, ai=NoAI())
    strategy.generate("xhs-developer")
    posts.create_post("xhs-developer", {"title": "首条作品", "views": 12})
    assert strategy.latest("xhs-developer")["status"] == "STALE"


def test_stale_baseline_or_diagnosis_blocks_recommendation(tmp_path):
    repository, _, posts, baseline_service = build(tmp_path, 5)
    strategy = StrategyRecommendationService(repository, ai=NoAI(), baselines=baseline_service)
    strategy.generate("douyin-pet")
    post = posts.list_posts("douyin-pet")[0]
    posts.update_post("douyin-pet", post.id, {"views": 999})
    assert strategy.latest("douyin-pet")["status"] == "STALE"
    with pytest.raises(ValueError, match="历史基准已过期"):
        strategy.generate("douyin-pet")


def test_stale_baseline_marks_current_recommendation_stale_even_if_diagnosis_is_current(tmp_path):
    repository, _, _, baseline_service = build(tmp_path, 5)
    strategy = StrategyRecommendationService(repository, ai=NoAI(), baselines=baseline_service)
    strategy.generate("douyin-pet")
    repository.mark_baseline_stale("douyin-pet")
    assert strategy.latest("douyin-pet")["status"] == "STALE"


def test_recommendation_versions_persist_without_activating_strategy(tmp_path):
    repository, accounts, _, baseline_service = build(tmp_path, 5)
    strategy = StrategyRecommendationService(repository, ai=NoAI(), baselines=baseline_service)
    v1 = strategy.generate("douyin-pet")
    v2 = strategy.generate("douyin-pet")
    assert v2["version"] == 2
    assert v2["status"] == "CURRENT"
    assert [item["status"] for item in strategy.history("douyin-pet")] == ["CURRENT", "SUPERSEDED"]
    assert accounts.get_account("douyin-pet").status.value == "DIAGNOSING"
    assert accounts.get_account("douyin-pet").strategy.state == "hypothesis"
    restarted = StrategyRecommendationService(OperatorAccountRepository(repository.db_path), ai=NoAI())
    assert restarted.latest("douyin-pet")["id"] == v2["id"]
    assert restarted.latest("douyin-pet")["recommendation"]["activation_status"] == "NOT_ACTIVATED"
    assert v1["id"] != v2["id"]


def test_profile_change_stales_the_recommendation(tmp_path):
    repository, accounts, _, baseline_service = build(tmp_path, 5)
    service = StrategyRecommendationService(repository, ai=NoAI(), baselines=baseline_service)
    service.generate("douyin-pet")
    accounts.update_account("douyin-pet", {"profileSummary": "更新后的账号资料假设"})
    assert service.latest("douyin-pet")["status"] == "STALE"


def test_unknown_subject_bias_prevents_sufficiency_even_when_groups_are_large():
    evidence = StrategyRecommendationService._subject_evidence_sufficiency({
        "sample_size": 82,
        "segments": {"subjects": {"coverage": 0.5488, "classified_sample_count": 45,
            "groups": [{"key": "缅因", "sample_size": 17},
                      {"key": "布偶", "sample_size": 17}, {"key": "双猫", "sample_size": 10}]}}
    })
    assert evidence["major_groups_sufficient"]
    assert evidence["unknown_count"] == 37
    assert evidence["unknown_could_change_comparison"]
    assert not evidence["sufficient"]
    assert evidence["note"] == "剩余未分类作品较多，主体间比较仍存在较大不确定性。"


def test_subject_evidence_sufficiency_requires_three_main_groups_and_bounded_unknowns():
    evidence = StrategyRecommendationService._subject_evidence_sufficiency({
        "sample_size": 20,
        "segments": {"subjects": {"coverage": 0.9, "classified_sample_count": 18,
            "groups": [{"key": "缅因", "sample_size": 6},
                      {"key": "布偶", "sample_size": 6}, {"key": "双猫", "sample_size": 6}]}}
    })
    assert evidence["unknown_bias_sufficient"]
    assert evidence["major_groups_sufficient"]
    assert evidence["coverage_sufficient"]
    assert evidence["sufficient"]


def test_strategy_recommendation_api_is_explicit_and_account_scoped(tmp_path):
    repository, _, _, baseline_service = build(tmp_path, 5)
    service = StrategyRecommendationService(repository, ai=NoAI(), baselines=baseline_service)
    app.dependency_overrides[get_strategy_recommendation_service] = lambda: service
    try:
        local = "http://localhost:7860"
        client = TestClient(app, base_url=local, headers={"Origin": local})
        assert client.get("/api/operator/accounts/douyin-pet/strategy-recommendations").json() is None
        generated = client.post("/api/operator/accounts/douyin-pet/strategy-recommendations")
        assert generated.status_code == 200
        assert generated.json()["recommendation"]["activation_status"] == "NOT_ACTIVATED"
        assert client.get("/api/operator/accounts/xhs-developer/strategy-recommendations").json() is None
        assert client.get("/api/operator/accounts/douyin-pet/strategy-recommendations/history").json()[0]["version"] == 1
        assert client.post("/api/operator/accounts/missing/strategy-recommendations").status_code == 404
    finally:
        app.dependency_overrides.pop(get_strategy_recommendation_service, None)
