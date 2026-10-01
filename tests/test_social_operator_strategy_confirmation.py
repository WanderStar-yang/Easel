from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import AccountNotActiveError, OperatorAccountService
from easel.social_operator.strategy_confirmation import StrategyConfirmationService


class StaticRecommendationService:
    def __init__(self, item):
        self.item = item

    def latest(self, account_id):
        return self.item if self.item and self.item["account_id"] == account_id else None


def _recommendation_body(sample_size=82):
    return {
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


def _setup(tmp_path, *, account_id="douyin-pet", sample_size=82, confidence="LOW"):
    repository = OperatorAccountRepository(tmp_path / "strategy.sqlite3")
    accounts = OperatorAccountService(repository)
    now = "2026-10-01T00:00:00+00:00"
    conn = sqlite3.connect(repository.db_path)
    conn.row_factory = sqlite3.Row
    if sample_size:
        conn.execute("UPDATE operator_accounts SET status = 'DIAGNOSING', diagnosis_completed_at = ? WHERE id = ?",
                     (now, account_id))
        conn.execute(
            "INSERT INTO account_diagnoses (id, account_id, algorithm_version, report_json, generated_at, status) "
            "VALUES (?, ?, 'test', '{}', ?, 'CURRENT')", ("diag-1", account_id, now),
        )
        conn.execute(
            "INSERT INTO account_baselines (id, account_id, version, sample_size, generated_at, "
            "historical_data_version, status, report_json) VALUES ('base-1', ?, 4, ?, ?, 'version', 'ACTIVE', '{}')",
            (account_id, sample_size, now),
        )
    conn.commit()
    conn.close()
    body = _recommendation_body(sample_size)
    body["confidence"] = confidence
    rec = repository.save_strategy_recommendation(
        "rec-v7", account_id, baseline_id="base-1" if sample_size else None,
        baseline_version=4 if sample_size else None, diagnosis_id="diag-1" if sample_size else None,
        generated_at=now, evidence_data_version="version", recommendation=body,
    )
    service = StrategyConfirmationService(repository, recommendations=StaticRecommendationService(rec))
    payload = {
        "recommendation_id": rec["id"],
        "positioning": body["positioning_hypothesis"]["summary"],
        "pillars": [{"recommendation_pillar_id": pillar["id"], "name": pillar["name"],
                     "description": pillar["description"], "allocation_ratio": pillar["initial_test_allocation"]}
                    for pillar in body["pillars"]],
    }
    return repository, accounts, service, rec, body, payload


def test_low_confidence_can_be_confirmed_and_active_gate_passes(tmp_path):
    repository, accounts, service, rec, body, payload = _setup(tmp_path)
    result = service.confirm("douyin-pet", payload)
    assert result["version"] == 1
    assert result["status"] == "ACTIVE"
    assert result["source_recommendation_id"] == rec["id"]
    assert result["confidence_at_confirmation"] == "LOW"
    assert [p["allocation_ratio"] for p in result["pillars"]] == [36, 31, 33]
    assert all(p["status"] == "ACTIVE" for p in result["pillars"])
    assert accounts.require_active_account("douyin-pet").status.value == "ACTIVE"
    assert result["experiment_plan"]["horizon_weeks"] == 4
    assert "缅因" in result["experiment_plan"]["tests"][0]["question"]
    assert "双猫互动" in result["experiment_plan"]["tests"][1]["question"]
    assert "趣味内容" in result["experiment_plan"]["tests"][2]["question"]


def test_ratio_must_total_100_and_confirmation_is_not_persisted(tmp_path):
    repository, accounts, service, _, _, payload = _setup(tmp_path)
    payload["pillars"][0]["allocation_ratio"] = 35
    with pytest.raises(ValueError, match="必须为 100%"):
        service.confirm("douyin-pet", payload)
    assert service.active("douyin-pet") is None
    assert accounts.get_account("douyin-pet").status.value == "DIAGNOSING"


def test_user_adjustments_are_saved_without_rewriting_recommendation(tmp_path):
    repository, _, service, rec, original, payload = _setup(tmp_path)
    payload["positioning"] = "双猫日常与关系互动实验"
    payload["pillars"][0].update(name="缅因日常观察", description="跟踪缅因日常内容的新表现", allocation_ratio=40)
    payload["pillars"][1]["allocation_ratio"] = 30
    payload["pillars"][2]["allocation_ratio"] = 30
    active = service.confirm("douyin-pet", payload)
    stored_recommendation = repository.get_latest_strategy_recommendation("douyin-pet")
    assert stored_recommendation["id"] == rec["id"]
    assert stored_recommendation["recommendation"] == original
    assert active["positioning"] == payload["positioning"]
    assert active["pillars"][0]["name"] == "缅因日常观察"
    assert active["pillars"][0]["description"] == "跟踪缅因日常内容的新表现"
    assert [p["allocation_ratio"] for p in active["pillars"]] == [40, 30, 30]


def test_only_one_active_strategy_and_second_confirmation_is_rejected(tmp_path):
    _, _, service, _, _, payload = _setup(tmp_path)
    service.confirm("douyin-pet", payload)
    with pytest.raises(ValueError, match="已经启用策略"):
        service.confirm("douyin-pet", payload)
    assert service.active("douyin-pet")["version"] == 1


def test_xiaohongshu_profile_only_strategy_can_be_explicitly_confirmed(tmp_path):
    _, accounts, service, _, _, payload = _setup(tmp_path, account_id="xhs-developer", sample_size=0)
    result = service.confirm("xhs-developer", payload)
    assert result["confidence_at_confirmation"] == "LOW"
    assert result["source_recommendation_id"] == payload["recommendation_id"]
    assert accounts.require_active_account("xhs-developer").status.value == "ACTIVE"


def test_confirmation_is_account_scoped_and_recommendation_must_match(tmp_path):
    _, _, service, _, _, payload = _setup(tmp_path)
    with pytest.raises(ValueError, match="当前有效"):
        service.confirm("xhs-developer", payload)
    assert service.active("douyin-pet") is None
    assert service.active("xhs-developer") is None


def test_stale_recommendation_or_baseline_cannot_be_confirmed(tmp_path):
    repository, _, service, _, _, payload = _setup(tmp_path)
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute("UPDATE strategy_recommendations SET status = 'STALE' WHERE id = 'rec-v7'")
    with pytest.raises(ValueError, match="已过期"):
        service.confirm("douyin-pet", payload)

    repository, _, service, _, _, payload = _setup(tmp_path / "baseline")
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute("UPDATE account_baselines SET status = 'STALE' WHERE id = 'base-1'")
    with pytest.raises(ValueError, match="Baseline"):
        service.confirm("douyin-pet", payload)

    repository, _, service, _, _, payload = _setup(tmp_path / "diagnosis")
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute("UPDATE account_diagnoses SET status = 'STALE' WHERE id = 'diag-1'")
    with pytest.raises(ValueError, match="诊断已过期"):
        service.confirm("douyin-pet", payload)


def test_profile_only_xhs_confirmation_is_rejected_if_historical_rows_exist(tmp_path):
    repository, _, service, _, _, payload = _setup(tmp_path, account_id="xhs-developer", sample_size=0)
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute(
            "INSERT INTO historical_posts (id, account_id, platform, title, content_source, created_at, updated_at) "
            "VALUES ('xhs-post', 'xhs-developer', 'xiaohongshu', '已有内容', 'UNKNOWN', 'now', 'now')"
        )
    with pytest.raises(ValueError, match="没有历史数据"):
        service.confirm("xhs-developer", payload)


def test_confirmation_audit_and_active_strategy_survive_restart(tmp_path):
    repository, _, service, rec, _, payload = _setup(tmp_path)
    first = service.confirm("douyin-pet", payload)
    restarted = StrategyConfirmationService(OperatorAccountRepository(repository.db_path),
                                            recommendations=StaticRecommendationService(rec))
    loaded = restarted.active("douyin-pet")
    assert loaded == first
    with sqlite3.connect(repository.db_path) as conn:
        event = conn.execute("SELECT account_id, recommendation_id, strategy_id, pillar_ratios_json "
                             "FROM strategy_confirmation_events").fetchone()
    assert event[:3] == ("douyin-pet", rec["id"], first["id"])
    assert json.loads(event[3]) == [36, 31, 33]


def test_audited_experiment_plan_repair_preserves_confirmed_pillar_ratios(tmp_path):
    repository, _, service, _, body, payload = _setup(tmp_path)
    active = service.confirm("douyin-pet", payload)
    pillars = [{**pillar, "recommendation_pillar_id": pillar["id"]} for pillar in body["pillars"]]
    corrected_plan = StrategyConfirmationService._experiment_plan(body, pillars)
    repaired = repository.repair_active_strategy_experiment_plan(
        "douyin-pet", active["id"], experiment_plan=corrected_plan,
        reason="test repair", occurred_at="2026-10-01T01:00:00+00:00",
    )
    assert [pillar["allocation_ratio"] for pillar in repaired["pillars"]] == [36, 31, 33]
    assert ["缅因" in item["question"] or "双猫" in item["question"] or "趣味" in item["question"]
            for item in repaired["experiment_plan"]["tests"]] == [True, True, True]
    with sqlite3.connect(repository.db_path) as conn:
        event = conn.execute("SELECT event_type, reason FROM strategy_active_change_events").fetchone()
    assert event == ("EXPERIMENT_PLAN_REPAIRED", "test repair")


def test_account_endpoint_exposes_active_version_after_confirmation(tmp_path):
    from web.app import app
    from web.routers.operator_accounts import get_service as get_accounts_service
    from web.routers.operator_strategy_confirmation import get_strategy_confirmation_service

    repository, accounts_service, service, _, _, payload = _setup(tmp_path)
    app.dependency_overrides[get_strategy_confirmation_service] = lambda: service
    app.dependency_overrides[get_accounts_service] = lambda: accounts_service
    try:
        local = "http://127.0.0.1:7860"
        with TestClient(app, base_url=local, client=("127.0.0.1", 51234), headers={"Origin": local}) as client:
            response = client.post("/api/operator/accounts/douyin-pet/strategy-confirmation", json=payload)
            assert response.status_code == 201, response.text
            assert response.json()["status"] == "ACTIVE"
            active = client.get("/api/operator/accounts/douyin-pet/active-strategy")
            assert active.status_code == 200
            assert active.json()["source_recommendation_id"] == payload["recommendation_id"]
            accounts = client.get("/api/operator/accounts").json()
            assert next(row for row in accounts if row["id"] == "douyin-pet")["status"] == "ACTIVE"
            invalid = {**payload, "pillars": [*payload["pillars"]]}
            invalid["pillars"][0] = {**invalid["pillars"][0], "allocation_ratio": 30}
            assert client.post("/api/operator/accounts/douyin-pet/strategy-confirmation", json=invalid).status_code == 409
    finally:
        app.dependency_overrides.pop(get_strategy_confirmation_service, None)
        app.dependency_overrides.pop(get_accounts_service, None)
