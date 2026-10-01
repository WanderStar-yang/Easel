from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from easel.ai_service import AIRuntimeState, AIRuntimeStatus
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from easel.social_operator.strategy_confirmation import StrategyConfirmationService
from easel.social_operator.topic_recommendations import TopicRecommendationService


class StaticRecommendationService:
    def __init__(self, item):
        self.item = item

    def latest(self, account_id):
        return self.item if self.item and self.item["account_id"] == account_id else None


def _setup(tmp_path, *, account_id="douyin-pet", sample_size=82):
    """Build an isolated confirmed-strategy fixture without importing another test module."""
    repository = OperatorAccountRepository(tmp_path / "strategy.sqlite3")
    accounts = OperatorAccountService(repository)
    now = "2026-10-01T00:00:00+00:00"
    body = {
        "status": "RECOMMENDED", "activation_status": "NOT_ACTIVATED", "confidence": "LOW",
        "confidence_note": "数据仍需验证。",
        "positioning_hypothesis": {"summary": "缅因猫与布偶猫双猫家庭", "evidence_level": "EXPERIMENTAL"},
        "audience_hypothesis": {"summary": "对猫咪日常和双猫相处感兴趣的观众"},
        "source": {"canonical_sample_size": sample_size, "baseline_version": 4},
        "evidence": [
            {"id": "subjects:缅因", "source": "Segment Baseline", "dimension": "subjects", "group": "缅因",
             "level": "SUPPORTED", "sample_size": 17, "views_median": 975,
             "engagement_rate_median": 0.0227, "baseline_difference": {"views": {"relative_change": 0.685}}},
            {"id": "subjects:双猫", "source": "Segment Baseline", "dimension": "subjects", "group": "双猫",
             "level": "SUPPORTED", "sample_size": 10, "views_median": 508,
             "engagement_rate_median": 0.0234, "baseline_difference": {"views": {"relative_change": -0.122}}},
            {"id": "content_type:搞笑/趣味", "source": "Segment Baseline", "dimension": "content_type",
             "group": "搞笑/趣味", "level": "SUPPORTED", "sample_size": 26, "views_median": 753,
             "engagement_rate_median": 0.0156},
        ],
        "pillars": [
            {"id": "p1", "name": "日常陪伴", "description": "记录日常", "initial_test_allocation": 36,
             "evidence_level": "SUPPORTED", "evidence_ids": ["subjects:缅因"], "goal": "测试持续性",
             "experiment_question": "缅因高播放能否持续？"},
            {"id": "p2", "name": "双猫互动", "description": "记录关系互动", "initial_test_allocation": 31,
             "evidence_level": "SUPPORTED", "evidence_ids": ["subjects:双猫"], "goal": "测试互动",
             "experiment_question": "双猫互动率能否持续高于整体？"},
            {"id": "p3", "name": "趣味记录", "description": "轻松趣味内容", "initial_test_allocation": 33,
             "evidence_level": "SUPPORTED", "evidence_ids": ["content_type:搞笑/趣味"], "goal": "测试互动",
             "experiment_question": "趣味表现是否稳定？"},
        ],
        "experiment_horizon_weeks": 4,
    }
    if sample_size:
        with sqlite3.connect(repository.db_path) as conn:
            conn.execute("UPDATE operator_accounts SET status = 'DIAGNOSING', diagnosis_completed_at = ? WHERE id = ?",
                         (now, account_id))
            conn.execute("INSERT INTO account_diagnoses "
                         "(id, account_id, algorithm_version, report_json, generated_at, status) "
                         "VALUES (?, ?, 'test', '{}', ?, 'CURRENT')", ("diag-1", account_id, now))
            conn.execute("INSERT INTO account_baselines "
                         "(id, account_id, version, sample_size, generated_at, historical_data_version, status, report_json) "
                         "VALUES ('base-1', ?, 4, ?, ?, 'version', 'ACTIVE', '{}')", (account_id, sample_size, now))
    recommendation = repository.save_strategy_recommendation(
        "rec-v7", account_id, baseline_id="base-1" if sample_size else None,
        baseline_version=4 if sample_size else None, diagnosis_id="diag-1" if sample_size else None,
        generated_at=now, evidence_data_version="version", recommendation=body,
    )
    confirmation = StrategyConfirmationService(
        repository, recommendations=StaticRecommendationService(recommendation),
    )
    payload = {
        "recommendation_id": recommendation["id"],
        "positioning": body["positioning_hypothesis"]["summary"],
        "pillars": [{"recommendation_pillar_id": pillar["id"], "name": pillar["name"],
                     "description": pillar["description"], "allocation_ratio": pillar["initial_test_allocation"]}
                    for pillar in body["pillars"]],
    }
    return repository, accounts, confirmation, recommendation, body, payload


class StructuredAI:
    def __init__(self):
        self.prompt = None

    def runtime_status(self):
        return AIRuntimeStatus(AIRuntimeState.AVAILABLE, "test provider")

    def complete(self, system_prompt, user_prompt):
        self.prompt = json.loads(user_prompt)
        return json.dumps({"topics": [
            {"pillar_id": pillar["id"], "title": f"可执行主题 {index + 1}",
             "angle": f"主题角度 {index + 1}",
             "description": f"拍摄一次真实场景，表达 {pillar['name']} 方向的观察，并测试对应实验问题。",
             "material_requirements": ["一次拍摄", "自然光"]}
            for index, pillar in enumerate(self.prompt["pillars"])
        ]}, ensure_ascii=False)


class NoAI:
    def runtime_status(self):
        return AIRuntimeStatus(AIRuntimeState.UNAVAILABLE)

    def complete(self, system_prompt, user_prompt):
        raise AssertionError("unavailable runtime should use the local fallback")


class UnsupportedExperienceAI(StructuredAI):
    def complete(self, system_prompt, user_prompt):
        self.prompt = json.loads(user_prompt)
        claims = [
            "我是如何从0到1跑通第一个MVP的？",
            "那个让我重构三次的架构设计问题",
            "AI Coding真的能让我每天少加两小时班吗？",
        ]
        return json.dumps({"topics": [
            {"pillar_id": pillar["id"], "title": claims[index], "angle": "复盘一次真实经历",
             "description": "展示本人项目过程与结果，并测试受众反馈。",
             "material_requirements": ["本人项目界面", "开发过程截图"]}
            for index, pillar in enumerate(self.prompt["pillars"])
        ]}, ensure_ascii=False)


def _active_douyin(tmp_path, ai=None):
    repository, _, confirmation, _, _, payload = _setup(tmp_path)
    confirmation.confirm("douyin-pet", payload)
    return repository, TopicRecommendationService(repository, ai=ai or StructuredAI())


def _active_xhs(tmp_path, ai=None):
    repository, _, confirmation, recommendation, body, payload = _setup(
        tmp_path, account_id="xhs-developer", sample_size=0,
    )
    # The shared Phase 6 test fixture models the Douyin case; remove those
    # deliberately synthetic segment references for the no-history XHS case.
    body["evidence"] = []
    for pillar in body["pillars"]:
        pillar["evidence_ids"] = []
    recommendation["recommendation"] = body
    confirmation.recommendations.item = recommendation
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute("UPDATE strategy_recommendations SET recommendation_json = ? WHERE id = ?",
                     (json.dumps(body, ensure_ascii=False), recommendation["id"]))
    confirmation.confirm("xhs-developer", payload)
    return repository, TopicRecommendationService(repository, ai=ai or StructuredAI())


def test_active_douyin_generates_three_grounded_topics_and_one_recommendation(tmp_path):
    repository, service = _active_douyin(tmp_path)
    ai = service.ai
    batch = service.generate("douyin-pet")

    assert len(batch["topics"]) == 3
    assert sum(item["status"] == "RECOMMENDED" for item in batch["topics"]) == 1
    assert {item["strategy_id"] for item in batch["topics"]} == {repository.get_active_strategy("douyin-pet")["id"]}
    assert {item["pillar_id"] for item in batch["topics"]} == {
        item["id"] for item in repository.get_active_strategy("douyin-pet")["pillars"]
    }
    assert batch["generation_mode"] == "AI"
    assert all(item["historical_evidence"] for item in batch["topics"])
    assert all(item["score_breakdown"]["weights_total"] == 100 for item in batch["topics"])
    assert all(item["score_breakdown"]["formula_version"] == "r1-topic-score-v1" for item in batch["topics"])
    assert "historical_top_low" in ai.prompt
    assert ai.prompt["overall_baseline"]["sample_size"] == 82
    assert "历史表现" not in json.dumps([item["title"] for item in batch["topics"]], ensure_ascii=False)
    assert service.today("douyin-pet")["today"]["id"] == batch["id"]


def test_daily_topic_batch_survives_repository_and_service_restart(tmp_path):
    repository, service = _active_douyin(tmp_path)
    batch = service.generate("douyin-pet")

    restarted_repository = OperatorAccountRepository(repository.db_path)
    restarted_service = TopicRecommendationService(restarted_repository, ai=NoAI())
    restored = restarted_service.today("douyin-pet")

    assert restored["today"]["id"] == batch["id"]
    assert restored["today"]["generation_mode"] == "AI"
    assert len(restored["today"]["topics"]) == 3


def test_low_confidence_does_not_block_and_score_weights_are_fixed(tmp_path):
    _, service = _active_douyin(tmp_path)
    batch = service.generate("douyin-pet")
    assert service.today("douyin-pet")["confidence"] == "LOW"
    for topic in batch["topics"]:
        breakdown = topic["score_breakdown"]
        assert {key: value["weight"] for key, value in breakdown["dimensions"].items()} == {
            "strategy_match": 30, "historical_support": 25, "experiment_value": 20,
            "execution_feasibility": 15, "freshness": 10,
        }
        assert topic["score"] == round(sum(value["contribution"] for value in breakdown["dimensions"].values()))
        assert "不是成功概率" in breakdown["note"]


def test_non_active_account_is_blocked_from_formal_generation_and_api(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "gate.sqlite3")
    service = TopicRecommendationService(repository, ai=NoAI())
    assert service.today("xhs-developer")["can_generate"] is False
    assert service.today("xhs-developer")["gate_reason"] == "尚未确认运营策略，暂不能生成正式选题。"
    with pytest.raises(ValueError, match="尚未确认运营策略"):
        service.generate("xhs-developer")

    from web.app import app
    from web.routers.operator_daily_topics import get_topic_service

    app.dependency_overrides[get_topic_service] = lambda: service
    try:
        local = "http://127.0.0.1:7860"
        with TestClient(app, base_url=local, client=("127.0.0.1", 51235), headers={"Origin": local}) as client:
            assert client.get("/api/operator/accounts/xhs-developer/daily-topics").json()["can_generate"] is False
            response = client.post("/api/operator/accounts/xhs-developer/daily-topics")
            assert response.status_code == 409
            assert "尚未确认运营策略" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_topic_service, None)


def test_xhs_profile_experiment_has_no_fabricated_history_and_uses_its_own_score(tmp_path):
    _, service = _active_xhs(tmp_path)
    batch = service.generate("xhs-developer")
    assert len(batch["topics"]) == 3
    assert sum(item["status"] == "RECOMMENDED" for item in batch["topics"]) == 1
    assert batch["generation_mode"] == "AI"
    for item in batch["topics"]:
        assert item["historical_evidence"] == []
        assert "没有历史表现数据" in item["recommendation_reason"]
        assert "本人真实项目经历" in item["recommendation_reason"]
        assert set(item["score_breakdown"]["dimensions"]) == {
            "positioning_match", "audience_value", "real_experience", "ip_value", "feasibility",
        }
        assert item["score_breakdown"]["weights_total"] == 100
        assert "真实" in item["description"] or "本人" in item["description"]


def test_xhs_unsupported_personal_history_or_numeric_claims_use_safe_templates(tmp_path):
    _, service = _active_xhs(tmp_path, ai=UnsupportedExperienceAI())

    batch = service.generate("xhs-developer")

    assert batch["generation_mode"] == "TEMPLATE"
    assert len(batch["topics"]) == 3
    assert sum(item["status"] == "RECOMMENDED" for item in batch["topics"]) == 1
    assert all(item["historical_evidence"] == [] for item in batch["topics"])
    serialized = json.dumps(batch["topics"], ensure_ascii=False)
    assert "重构三次" not in serialized
    assert "少加两小时" not in serialized
    assert "从0到1跑通" not in serialized


def test_ai_unavailable_uses_labeled_local_template_and_does_not_modify_evidence(tmp_path):
    _, service = _active_douyin(tmp_path, ai=NoAI())
    batch = service.generate("douyin-pet")
    assert batch["generation_mode"] == "TEMPLATE"
    assert len(batch["topics"]) == 3
    assert sum(item["status"] == "RECOMMENDED" for item in batch["topics"]) == 1
    assert all(item["historical_evidence"] for item in batch["topics"])
    assert service.today("douyin-pet")["generation_mode"] == "TEMPLATE"


def test_regeneration_skips_old_candidates_and_similarity_reduces_freshness(tmp_path):
    repository, service = _active_douyin(tmp_path)
    first = service.generate("douyin-pet")
    first_ids = [item["id"] for item in first["topics"]]
    second = service.generate("douyin-pet")
    assert second["batch_number"] == 2
    with sqlite3.connect(repository.db_path) as conn:
        statuses = [row[0] for row in conn.execute(
            f"SELECT status FROM operator_topics WHERE id IN ({','.join('?' for _ in first_ids)})", first_ids,
        )]
    assert statuses == ["SKIPPED", "SKIPPED", "SKIPPED"]
    assert all(item["score_breakdown"]["dimensions"]["freshness"]["score"] < 100
               for item in second["topics"])
    assert second["topics"][0]["similarity_score"] > 0


def test_selection_is_account_scoped_single_choice_and_audited(tmp_path):
    repository, service = _active_douyin(tmp_path)
    batch = service.generate("douyin-pet")
    chosen = next(item for item in batch["topics"] if item["status"] == "CANDIDATE")
    updated = service.select("douyin-pet", chosen["id"])
    assert sum(item["status"] == "SELECTED" for item in updated["topics"]) == 1
    assert all(item["status"] in {"SELECTED", "SKIPPED"} for item in updated["topics"])
    with pytest.raises(ValueError, match="今天已经选择"):
        service.select("douyin-pet", batch["topics"][0]["id"])

    from easel.social_operator.strategy_recommendations import StrategyRecommendationService

    recommendations = StrategyRecommendationService(repository, ai=NoAI())
    xhs_rec = recommendations.generate("xhs-developer")
    xhs_body = xhs_rec["recommendation"]
    xhs_payload = {
        "recommendation_id": xhs_rec["id"],
        "positioning": xhs_body["positioning_hypothesis"]["summary"],
        "pillars": [{"recommendation_pillar_id": pillar["id"], "name": pillar["name"],
                     "description": pillar["description"],
                     "allocation_ratio": pillar["initial_test_allocation"]}
                    for pillar in xhs_body["pillars"]],
    }
    StrategyConfirmationService(repository, recommendations=recommendations).confirm("xhs-developer", xhs_payload)
    with pytest.raises(ValueError, match="不属于当前账号"):
        service.select("xhs-developer", chosen["id"])
    with sqlite3.connect(repository.db_path) as conn:
        event = conn.execute("SELECT event_type, account_id, topic_id FROM operator_topic_events").fetchone()
    assert event == ("TOPIC_SELECTED", "douyin-pet", chosen["id"])


def test_xhs_template_fallback_has_first_person_fact_check_and_no_history(tmp_path):
    _, service = _active_xhs(tmp_path, ai=NoAI())
    batch = service.generate("xhs-developer")
    assert batch["generation_mode"] == "TEMPLATE"
    assert all(item["historical_evidence"] == [] for item in batch["topics"])
    assert all("本人" in item["description"] or "真实项目" in item["description"]
               for item in batch["topics"])
