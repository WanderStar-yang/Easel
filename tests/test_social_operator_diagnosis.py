from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from easel.social_operator.diagnosis import (
    AccountDiagnosisService,
    InsufficientHistoryError,
    UnavailableExplainer,
)
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from easel.social_operator.historical import HistoricalPostService
from easel.social_operator.historical_imports import HistoricalImportManager
from web.routers.historical_posts import HistoricalServices, get_historical_services
from web.routers.operator_diagnosis import get_diagnosis_service


@pytest.fixture
def services(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "operator.sqlite3")
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    diagnosis = AccountDiagnosisService(repository, explainer=UnavailableExplainer())
    return repository, accounts, posts, diagnosis


def _douyin_sample(services, count=12):
    _, _, posts, _ = services
    start = datetime(2025, 1, 1, 19, tzinfo=timezone.utc)
    created = []
    for index in range(count):
        source = "REAL" if index < count // 2 else "AI"
        views = 500 if source == "REAL" else 200
        created.append(posts.create_post("douyin-pet", {
            "title": f"{source} 内容 {index}",
            "publish_time": (start + timedelta(days=index)).isoformat(),
            "content_type": "双猫互动" if index % 2 == 0 else "单猫日常",
            "content_source": source,
            "subjects": ["缅因", "布偶"] if index % 2 == 0 else ["缅因"],
            "hook_type": "提问" if index % 3 else None,
            "duration": 20 if index % 2 else 12,
            "views": views + index,
            "likes": 50 + index,
            "comments": 10 + index,
            "favorites": 5 + index,
            "shares": 2 + index,
            "followers_gain": index - 2,
        }))
    return created


def test_empty_history_does_not_create_fake_report_or_advance_state(services):
    repository, accounts, _, diagnosis = services
    with pytest.raises(InsufficientHistoryError, match="暂无历史内容"):
        diagnosis.diagnose("douyin-pet")
    assert repository.get_latest_diagnosis("douyin-pet") is None
    assert accounts.get_account("douyin-pet").status.value == "NEW"
    assert repository.get_account("douyin-pet")["diagnosis_completed_at"] is None


def test_one_or_two_posts_are_allowed_but_low_confidence(services):
    _, accounts, posts, diagnosis = services
    posts.create_post("douyin-pet", {"title": "只有一条", "views": 10, "likes": 1})
    report = diagnosis.diagnose("douyin-pet").as_dict()
    assert report["data_quality"]["sample_size"] == 1
    assert report["confidence"] == "LOW"
    assert report["metric_summary"]["views"]["median"] == 10
    assert report["ai_explanation"]["status"] == "unavailable"
    assert accounts.get_account("douyin-pet").status.value == "DIAGNOSING"
    assert accounts.get_account("douyin-pet").diagnosis_completed_at == report["generated_at"]
    assert report["account"]["status"] == "DIAGNOSING"


def test_douyin_medians_engagement_top_low_and_real_vs_ai_findings(services):
    _, _, _, diagnosis = services
    created = _douyin_sample(services, 12)
    report = diagnosis.diagnose("douyin-pet").as_dict()
    assert report["platform"] == "douyin"
    assert report["metric_summary"]["views"]["median"] == 355.5
    assert report["metric_summary"]["likes"]["median"] == 55.5
    assert report["metric_summary"]["engagement_rate"]["formula"].startswith("sum(available likes")
    expected_rates = sorted(
        (50 + index + 10 + index + 5 + index + 2 + index) / (500 + index if index < 6 else 200 + index)
        for index in range(12)
    )
    expected_rate_median = (expected_rates[5] + expected_rates[6]) / 2
    assert report["metric_summary"]["engagement_rate"]["median"] == pytest.approx(expected_rate_median)
    assert report["top_posts"][0]["id"] == created[5].id
    assert report["low_posts"][0]["id"] == created[6].id
    assert all(post["rank_basis"] == "views_desc" for post in report["top_posts"])
    finding = next(item for item in report["pattern_findings"]
                   if item["dimension"] == "content_source" and item["metric"] == "views_median")
    assert finding["pattern"] == "REAL vs AI"
    assert finding["sample_a"] == finding["sample_b"] == 6
    assert finding["confidence"] == "MEDIUM"
    assert report["content_distribution"]["subjects"]["双猫"] == 6
    assert report["content_distribution"]["content_source"] == {"REAL": 6, "AI": 6}
    assert report["account_context"]["used_as_conclusion_source"] is False


def test_small_group_comparisons_are_low_confidence_not_asserted_as_facts(services):
    _, _, posts, diagnosis = services
    posts.create_post("douyin-pet", {"title": "单条双猫", "views": 900,
                                      "content_type": "双猫互动", "subjects": ["缅因", "布偶"]})
    posts.create_post("douyin-pet", {"title": "单条单猫", "views": 100,
                                      "content_type": "单猫日常", "subjects": ["缅因"]})
    report = diagnosis.diagnose("douyin-pet").as_dict()
    assert not any(item["dimension"] == "content_type" and item["metric"] == "views_median"
                   for item in report["pattern_findings"])
    assert any("content_type" in item for item in report["insufficient_data"])
    assert report["confidence"] == "LOW"


def test_missing_metrics_stay_missing_and_coverage_is_reported(services):
    _, _, posts, diagnosis = services
    posts.create_post("douyin-pet", {"title": "无指标"})
    posts.create_post("douyin-pet", {"title": "有播放", "views": 0, "likes": 5})
    report = diagnosis.diagnose("douyin-pet").as_dict()
    assert report["metric_summary"]["comments"]["median"] is None
    assert report["metric_summary"]["comments"]["available"] == 0
    assert report["metric_summary"]["views"]["median"] == 0
    assert report["metric_summary"]["engagement_rate"]["available"] == 0
    assert report["data_quality"]["metric_coverage"]["views"]["coverage"] == 0.5


def test_high_confidence_requires_large_complete_sample(services):
    _, _, _, diagnosis = services
    _douyin_sample(services, 24)
    report = diagnosis.diagnose("douyin-pet").as_dict()
    assert report["confidence"] == "HIGH"
    assert report["data_quality"]["completeness"]["score"] == 100
    assert report["data_quality"]["confidence_rules"]["HIGH"]


def test_xhs_metrics_save_signal_and_ip_business_signals(services):
    _, _, posts, diagnosis = services
    for index in range(8):
        posts.create_post("xhs-developer", {
            "title": f"项目笔记 {index}", "publish_time": f"2025-02-{index + 1:02d}",
            "content_type": "项目复盘" if index < 4 else "AI Coding",
            "exposure": 1000 + index * 100, "likes": 20 + index,
            "favorites": 30 + index, "comments": 4 + index,
            "shares": 2, "followers_gain": index,
            "profile_visits": 50 + index, "inquiries": index % 2,
        })
    report = diagnosis.diagnose("xhs-developer").as_dict()
    assert report["platform"] == "xiaohongshu"
    assert report["metric_summary"]["views"]["median"] == 1350
    assert report["metric_summary"]["profile_visits"]["median"] == 53.5
    assert report["metric_summary"]["inquiries"]["median"] == 0.5
    assert report["content_distribution"]["content_type"] == {"项目复盘": 4, "AI Coding": 4}
    assert report["top_posts"][0]["title"] == "项目笔记 7"
    assert report["top_posts"][0]["rank_basis"] == "favorites_desc"
    assert report["save_value_signal"]["observed"] is True
    assert report["ip_business_signals"]["profile_visits_median"] == 53.5
    assert "不调整 Strategy" in report["ip_business_signals"]["interpretation"]


def test_low_completeness_keeps_diagnosis_available_but_confidence_low(services):
    _, _, posts, diagnosis = services
    for index in range(6):
        posts.create_post("xhs-developer", {"title": f"标题 {index}"})
    report = diagnosis.diagnose("xhs-developer").as_dict()
    assert report["confidence"] == "LOW"
    assert report["data_quality"]["completeness"]["score"] == 20
    assert any("完整度" in item for item in report["problems"])


def test_diagnosis_isolated_between_accounts_and_persisted_across_restart(services, tmp_path):
    repository, _, posts, diagnosis = services
    _douyin_sample(services, 5)
    posts.create_post("xhs-developer", {"title": "另一个账号笔记", "views": 5000, "likes": 500})
    first = diagnosis.diagnose("douyin-pet")
    second = diagnosis.diagnose("xhs-developer")
    assert first.as_dict()["account_id"] == "douyin-pet"
    assert second.as_dict()["account_id"] == "xhs-developer"
    assert second.as_dict()["top_posts"][0]["title"] == "另一个账号笔记"
    assert diagnosis.list_history("douyin-pet")[-1].account_id == "douyin-pet"
    restarted = AccountDiagnosisService(
        OperatorAccountRepository(tmp_path / "operator.sqlite3"), explainer=UnavailableExplainer(),
    )
    assert restarted.get_latest("douyin-pet").id == first.id
    assert restarted.get_latest("xhs-developer").id == second.id
    assert repository.get_account("douyin-pet")["diagnosis_completed_at"] == first.generated_at


def test_diagnosis_does_not_advance_to_strategy_or_active(services):
    _, accounts, posts, diagnosis = services
    posts.create_post("douyin-pet", {"title": "一条历史", "views": 100})
    diagnosis.diagnose("douyin-pet")
    account = accounts.get_account("douyin-pet")
    assert account.status.value == "DIAGNOSING"
    assert account.strategy.state == "hypothesis"


def test_engine_runs_without_any_explainer_or_model_key(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "no-model.sqlite3")
    accounts = OperatorAccountService(repository)
    HistoricalPostService(repository).create_post("douyin-pet", {
        "title": "无模型诊断", "views": 240, "likes": 12,
    })
    report = AccountDiagnosisService(repository).diagnose("douyin-pet").as_dict()
    assert report["metric_summary"]["views"]["median"] == 240
    assert report["ai_explanation"]["status"] == "unavailable"
    assert report["strengths"] and report["problems"] and report["opportunities"]
    assert accounts.get_account("douyin-pet").status.value == "DIAGNOSING"


def test_api_diagnosis_routes_isolation_empty_guard_and_phase2_compatibility(services):
    _, _, posts, diagnosis = services
    posts.create_post("douyin-pet", {"title": "API 历史", "views": 100, "likes": 5})
    from web.app import app

    app.dependency_overrides[get_diagnosis_service] = lambda: diagnosis
    app.dependency_overrides[get_historical_services] = lambda: HistoricalServices(
        services[1], posts, HistoricalImportManager(posts, services[0]),
    )
    try:
        local = "http://127.0.0.1:7860"
        with TestClient(app, base_url=local, client=("127.0.0.1", 51235),
                        headers={"Origin": local}) as client:
            empty = client.post("/api/operator/accounts/xhs-developer/diagnosis")
            assert empty.status_code == 409
            assert empty.json()["detail"]["code"] == "INSUFFICIENT_DATA"
            created = client.post("/api/operator/accounts/douyin-pet/diagnosis")
            assert created.status_code == 200, created.text
            assert created.json()["account_id"] == "douyin-pet"
            assert client.get("/api/operator/accounts/xhs-developer/diagnosis").status_code == 404
            assert client.get("/api/operator/accounts/douyin-pet/diagnosis").json()["id"] == created.json()["id"]
            assert client.get("/api/operator/accounts/douyin-pet/diagnosis/history").json()[0]["id"] == created.json()["id"]
            assert client.get("/api/operator/accounts/douyin-pet/posts").json()["total"] == 1
            assert client.get("/api/accounts").status_code == 200
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)
        app.dependency_overrides.pop(get_historical_services, None)
