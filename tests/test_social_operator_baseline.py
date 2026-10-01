from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from easel.social_operator.baselines import AccountBaselineService
from easel.social_operator.diagnosis import AccountDiagnosisService
from easel.social_operator.historical import HistoricalPostService
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from easel.social_operator.snapshot_reconciliation import SnapshotReconciliationManager
from web.app import app
from web.routers.operator_baselines import get_baseline_service


def setup_baseline(tmp_path, count=8, *, views=None):
    repository = OperatorAccountRepository(tmp_path / "baseline.sqlite3")
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    start = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    for index in range(count):
        view_count = views[index] if views else (100 + index * 100)
        posts.create_post("douyin-pet", {
            "title": f"作品 {index}", "publish_time": (start + timedelta(days=index)).isoformat(),
            "content_type": "双猫互动" if index % 2 == 0 else "单猫日常",
            "content_source": "REAL" if index < count // 2 else "AI",
            "subjects": ["缅因", "布偶"] if index % 2 == 0 else ["缅因"],
            "hook_type": "提问" if index % 2 == 0 else None,
            "duration": 12 if index % 2 == 0 else 25,
            "views": view_count, "likes": index if index % 2 else 0,
            "comments": 1 if index % 3 else None,
            "favorites": 0 if index % 2 else None, "shares": 2,
            "followers_gain": index - 2,
        })
    diagnosis = AccountDiagnosisService(repository)
    diagnosis.diagnose("douyin-pet")
    return repository, accounts, posts, diagnosis, AccountBaselineService(repository)


def test_baseline_uses_canonical_unique_posts_and_ignores_duplicate_rows(tmp_path):
    repository, _, _, _, service = setup_baseline(tmp_path, 3)
    with repository._connect() as conn:
        conn.execute("DROP INDEX idx_historical_posts_platform_id")
        conn.execute(
            "INSERT INTO historical_posts (id, account_id, platform, publish_time, title, content_source, "
            "tags_json, subjects_json, platform_post_id, views, data_source, source_presence, created_at, updated_at) "
            "SELECT 'duplicate-row', account_id, platform, publish_time, title, content_source, tags_json, "
            "subjects_json, platform_post_id, 999999, 'DOUYIN_CREATOR_CENTER', source_presence, created_at, updated_at "
            "FROM historical_posts WHERE id = (SELECT id FROM historical_posts WHERE account_id = 'douyin-pet' LIMIT 1)"
        )
    report = service.preview("douyin-pet")
    assert report["sample_size"] == 3
    assert report["metrics"]["views"]["median"] == 200


def test_median_percentiles_and_extreme_outlier(tmp_path):
    _, _, _, _, service = setup_baseline(tmp_path, 5, views=[100, 200, 300, 400, 693000])
    result = service.preview("douyin-pet")
    assert result["metrics"]["views"]["median"] == 300
    assert result["metrics"]["views"]["p25"] == 200
    assert result["metrics"]["views"]["p75"] == 400


def test_missing_is_not_zero_real_zero_counts_and_metric_coverage(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "missing.sqlite3")
    OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    posts.create_post("douyin-pet", {"title": "真实零", "views": 0, "likes": 0})
    posts.create_post("douyin-pet", {"title": "缺失指标"})
    AccountDiagnosisService(repository).diagnose("douyin-pet")
    result = AccountBaselineService(repository).preview("douyin-pet")
    assert result["sample_size"] == 2
    assert result["metrics"]["views"]["median"] == 0
    assert result["metrics"]["views"]["sample_count"] == 1
    assert result["metrics"]["views"]["coverage"] == 0.5
    assert result["metrics"]["comments"]["median"] is None
    assert result["metrics"]["comments"]["sample_count"] == 0
    assert result["metrics"]["comments"]["coverage"] == 0


def test_engagement_uses_available_components_per_post_and_positive_views_only(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "engagement.sqlite3")
    OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    posts.create_post("douyin-pet", {"title": "部分互动", "views": 100, "likes": 10, "comments": None})
    posts.create_post("douyin-pet", {"title": "零播放", "views": 0, "likes": 100})
    posts.create_post("douyin-pet", {"title": "真实零互动", "views": 100, "likes": 0, "comments": 0})
    AccountDiagnosisService(repository).diagnose("douyin-pet")
    metric = AccountBaselineService(repository).preview("douyin-pet")["metrics"]["engagement_rate"]
    assert metric["sample_count"] == 2
    assert metric["median"] == 0.05
    assert metric["coverage"] == pytest.approx(2 / 3)


def test_overall_baseline_works_without_classification_and_unparsed_metrics_are_null(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "overall.sqlite3")
    OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    posts.create_post("douyin-pet", {"title": "一", "views": 100})
    posts.create_post("douyin-pet", {"title": "二", "views": 200})
    AccountDiagnosisService(repository).diagnose("douyin-pet")
    result = AccountBaselineService(repository).preview("douyin-pet")
    assert result["sample_size"] == 2
    assert result["metrics"]["views"]["median"] == 150
    assert result["metrics"]["completion_rate"]["median"] is None
    assert result["metrics"]["two_sec_bounce_rate"]["median"] is None
    assert result["metrics"]["avg_watch_duration"]["median"] is None
    assert result["segments"]["content_type"]["groups"] == []


def test_classified_segment_baseline_threshold_and_formal_comparison_threshold(tmp_path):
    _, _, _, _, service = setup_baseline(tmp_path, 4)
    result = service.preview("douyin-pet")
    groups = result["segments"]["content_type"]["groups"]
    assert all(group["sample_size"] == 2 for group in groups)
    assert not groups  # two per segment is below the three-post display minimum

    repository = OperatorAccountRepository(tmp_path / "segments.sqlite3")
    OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    for index in range(8):
        posts.create_post("douyin-pet", {"title": f"classified {index}", "content_type": "真实分类",
                                          "content_source": "REAL", "views": index * 10})
    AccountDiagnosisService(repository).diagnose("douyin-pet")
    segment = AccountBaselineService(repository).preview("douyin-pet")["segments"]["content_type"]["groups"][0]
    assert segment["sample_size"] == 8
    assert segment["eligible_for_comparison"] is True


def test_three_post_group_is_shown_but_not_formal_comparison(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "three.sqlite3")
    OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    for index in range(3):
        posts.create_post("douyin-pet", {"title": f"分类 {index}", "content_type": "三条组", "views": 100 + index})
    AccountDiagnosisService(repository).diagnose("douyin-pet")
    group = AccountBaselineService(repository).preview("douyin-pet")["segments"]["content_type"]["groups"][0]
    assert group["sample_size"] == 3
    assert group["eligible_for_comparison"] is False


def test_segment_reports_descriptive_difference_from_overall_medians(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "difference.sqlite3")
    OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    for index, views in enumerate((100, 200, 300, 400, 1000, 1200)):
        posts.create_post("douyin-pet", {
            "title": f"分类作品 {index}", "content_type": "较高组" if index >= 3 else "较低组",
            "views": views, "likes": 10,
        })
    AccountDiagnosisService(repository).diagnose("douyin-pet")
    preview = AccountBaselineService(repository).preview("douyin-pet")
    groups = {row["key"]: row for row in preview["segments"]["content_type"]["groups"]}
    overall = preview["metrics"]["views"]["median"]
    high = groups["较高组"]
    assert high["baseline_difference"]["views"]["overall_median"] == overall
    assert high["baseline_difference"]["views"]["segment_median"] == high["metrics"]["views"]["median"]
    assert high["baseline_difference"]["views"]["relative_change"] == (
        high["metrics"]["views"]["median"] / overall - 1
    )


def test_version_1_regenerate_version_2_keeps_history_and_only_one_active(tmp_path):
    repository, _, posts, _, service = setup_baseline(tmp_path, 5)
    v1 = service.generate("douyin-pet")
    assert v1.version == 1 and v1.status == "ACTIVE"
    posts.create_post("douyin-pet", {"title": "后来补录", "views": 900})
    AccountDiagnosisService(repository).diagnose("douyin-pet")
    preview = service.preview("douyin-pet")
    v2 = service.generate("douyin-pet", preview["historical_data_version"])
    versions = service.history("douyin-pet")
    assert v2.version == 2 and v2.status == "ACTIVE"
    assert [item.status for item in versions] == ["ACTIVE", "STALE"]


def test_baseline_stales_on_historical_create_update_classification_and_delete(tmp_path):
    _, _, posts, _, service = setup_baseline(tmp_path, 5)
    baseline = service.generate("douyin-pet")
    assert service.latest("douyin-pet").status == "ACTIVE"
    post = posts.list_posts("douyin-pet")[0]
    posts.update_post("douyin-pet", post.id, {"views": (post.views or 0) + 1})
    assert service.latest("douyin-pet").status == "STALE"
    # Regeneration still requires the diagnosis to be current.
    AccountDiagnosisService(service.repository).diagnose("douyin-pet")
    current = service.generate("douyin-pet")
    service.repository.classify_posts("douyin-pet", [post.id], {"content_source": "REAL"}, "2026-01-01T00:00:00+00:00")
    assert service.latest("douyin-pet").status == "STALE"
    assert service.history("douyin-pet")[-1].id == baseline.id
    assert current.version == 2
    AccountDiagnosisService(service.repository).diagnose("douyin-pet")
    service.generate("douyin-pet")
    service.repository.delete_post("douyin-pet", post.id)
    assert service.latest("douyin-pet").status == "STALE"


def test_baseline_stales_after_confirmed_historical_repair(tmp_path):
    repository, _, posts, _, service = setup_baseline(tmp_path, 5)
    service.generate("douyin-pet")
    original = posts.list_posts("douyin-pet")[0]
    duplicate_id = "legacy-repair-copy"
    now = "2026-09-30T00:00:00+00:00"
    with repository._connect() as conn:
        conn.execute(
            "INSERT INTO historical_posts (id, account_id, platform, publish_time, title, content_source, "
            "tags_json, subjects_json, views, data_source, source_presence, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'UNKNOWN', '[]', '[]', 1, 'DOUYIN_CREATOR_CENTER', 'PRESENT', ?, ?)",
            (duplicate_id, "douyin-pet", "douyin", original.publish_time, original.title, now, now),
        )
    snapshots = SnapshotReconciliationManager(repository)
    preview = snapshots.preview_repair("douyin-pet")
    assert preview["auto_merge_count"] == 1
    result = snapshots.confirm_repair("douyin-pet", preview["preview_id"])
    assert result["archived_duplicate_count"] == 1
    assert service.latest("douyin-pet").status == "STALE"

def test_account_isolation_and_future_comparison_contract(tmp_path):
    _, _, _, _, service = setup_baseline(tmp_path, 5)
    service.generate("douyin-pet")
    assert service.latest("xhs-developer") is None
    with pytest.raises(ValueError, match="没有可用的历史基准"):
        service.compare_to_baseline("xhs-developer", {"views": 100})
    comparison = service.compare_to_baseline("douyin-pet", {"views": 900, "likes": 8, "engagement_rate": 0.03})
    assert comparison["metrics"]["views"]["baseline_median"] == 300
    assert comparison["metrics"]["views"]["range"] == "above_typical"


def test_restart_persistence_and_baseline_requires_current_diagnosis(tmp_path):
    repository, _, _, _, service = setup_baseline(tmp_path, 5)
    baseline = service.generate("douyin-pet")
    restarted = AccountBaselineService(OperatorAccountRepository(repository.db_path))
    assert restarted.latest("douyin-pet").id == baseline.id
    assert restarted.latest("douyin-pet").sample_size == 5

    with repository._connect() as conn:
        conn.execute("UPDATE account_diagnoses SET status = 'STALE' WHERE account_id = 'douyin-pet'")
    with pytest.raises(ValueError, match="诊断已过期"):
        restarted.preview("douyin-pet")


def test_preview_confirmation_detects_changed_historical_version(tmp_path):
    _, _, posts, _, service = setup_baseline(tmp_path, 5)
    preview = service.preview("douyin-pet")
    posts.create_post("douyin-pet", {"title": "预览后新增", "views": 50})
    with pytest.raises(ValueError, match="预览后发生了变化"):
        service.generate("douyin-pet", preview["historical_data_version"])


def test_api_preview_generate_and_compare_account_scoped(tmp_path):
    repository, _, _, _, service = setup_baseline(tmp_path, 5)
    app.dependency_overrides[get_baseline_service] = lambda: service
    try:
        local = "http://localhost:7860"
        client = TestClient(app, base_url=local, headers={"Origin": local})
        preview = client.post("/api/operator/accounts/douyin-pet/baseline/preview")
        assert preview.status_code == 200
        data = preview.json()
        assert data["sample_size"] == 5
        result = client.post("/api/operator/accounts/douyin-pet/baseline", json={
            "historical_data_version": data["historical_data_version"],
        })
        assert result.status_code == 200 and result.json()["version"] == 1
        assert client.get("/api/operator/accounts/douyin-pet/baseline").json()["status"] == "ACTIVE"
        assert client.post("/api/operator/accounts/douyin-pet/baseline/compare", json={
            "metrics": {"views": 500, "likes": 4, "engagement_rate": 0.02},
        }).status_code == 200
        assert client.get("/api/operator/accounts/xhs-developer/baseline").json() is None
    finally:
        app.dependency_overrides.pop(get_baseline_service, None)
