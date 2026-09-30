from __future__ import annotations

import json
from datetime import datetime, timezone

from easel.social_operator.canonical import canonical_unique_posts, clean_title
from easel.social_operator.diagnosis import AccountDiagnosisService
from easel.social_operator.historical import HistoricalPostService
from easel.social_operator.intelligence import AccountIntelligenceEngine, confidence_level
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from easel.social_operator.snapshot_reconciliation import SnapshotReconciliationManager
from easel.social_operator.historical_imports import HistoricalImportManager
from fastapi.testclient import TestClient
from web.app import app
from web.routers.historical_posts import HistoricalServices, get_historical_services


def make_repo(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "social.sqlite3")
    OperatorAccountService(repository)
    return repository


def test_canonical_view_deduplicates_top_low_and_excludes_stale_snapshot_rows():
    rows = [
        {"id": "first", "platform_post_id": "post-1", "title": "作品", "views": 100, "source_presence": "PRESENT"},
        {"id": "copy", "platform_post_id": "post-1", "title": "作品 编辑作品 设置权限 作品置顶 删除作品", "views": 1, "source_presence": "PRESENT"},
        {"id": "old", "platform_post_id": "post-2", "title": "旧作品", "views": 999, "source_presence": "MISSING"},
    ]
    unique = canonical_unique_posts(rows)
    assert [row["id"] for row in unique] == ["first"]
    assert unique[0]["title"] == "作品"


def test_title_cleanup_handles_creator_controls_without_changing_normal_titles():
    assert clean_title("视频标题 编辑作品 设置权限 取消置顶 删除作品") == "视频标题"
    assert clean_title("普通作品标题") == "普通作品标题"


def test_report_uses_unique_posts_and_missing_hook_or_duration_stays_unknown(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    posts.create_post("douyin-pet", {"title": "有指标", "publish_time": "2026-01-01", "views": 100,
                                      "likes": 5, "duration": 0})
    report = AccountDiagnosisService(repo).diagnose("douyin-pet").as_dict()
    assert report["data_quality"]["sample_size"] == 1
    assert report["record_counts"]["unique_post_count"] == report["record_counts"]["diagnosis_sample_count"] == 1
    assert report["data_gaps"][-1]["label"] == "开场方式"
    assert "Hook 信息未分析" in report["data_gaps"][-1]["impact"]
    assert any(item["field"] == "duration" and item["missing_count"] == 1 for item in report["data_gaps"])
    assert "无 Hook" not in str(report["content_distribution"])
    assert report["content_distribution"]["duration"] == {}


def test_deterministic_summary_is_not_replaced_by_unverified_llm_text(tmp_path):
    class HallucinatingExplainer:
        def explain(self, report):
            return {"status": "available", "provider": "test", "summary": "该账号有 999999 次播放", "reason": None}

    repo = make_repo(tmp_path)
    HistoricalPostService(repo).create_post("douyin-pet", {"title": "基准作品", "views": 120, "likes": 8})
    report = AccountDiagnosisService(repo, explainer=HallucinatingExplainer()).diagnose("douyin-pet").as_dict()
    assert "120" in report["overview"]
    assert "999999" not in report["overview"]
    assert report["ai_explanation"]["summary"] == "该账号有 999999 次播放"


def test_raw_count_and_top_low_use_only_canonical_posts(tmp_path):
    repo = make_repo(tmp_path)
    post = HistoricalPostService(repo).create_post("douyin-pet", {
        "title": "同一作品", "publish_time": "2026-02-01", "views": 800, "likes": 10,
    })
    with repo._connect() as conn:
        conn.execute(
            "INSERT INTO historical_posts (id, account_id, platform, publish_time, title, content_source, "
            "tags_json, subjects_json, views, likes, data_source, source_presence, created_at, updated_at) "
            "SELECT 'duplicate-copy', account_id, platform, publish_time, title, content_source, tags_json, "
            "subjects_json, 5, 1, data_source, source_presence, created_at, updated_at "
            "FROM historical_posts WHERE id = ?", (post.id,),
        )
    report = AccountDiagnosisService(repo).diagnose("douyin-pet").as_dict()
    assert report["record_counts"]["raw_record_count"] == 2
    assert report["record_counts"]["unique_post_count"] == 1
    assert report["record_counts"]["diagnosis_sample_count"] == 1
    assert len(report["top_posts"]) == len(report["low_posts"]) == 1
    assert report["top_posts"][0]["id"] == report["low_posts"][0]["id"]


def test_stale_report_is_marked_and_kept_separate_from_latest_facts(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    posts.create_post("douyin-pet", {"title": "旧作品", "views": 80})
    service = AccountDiagnosisService(repo)
    old = service.diagnose("douyin-pet")
    with repo._connect() as conn:
        repo._mark_diagnoses_stale(conn, "douyin-pet", "2026-09-30T10:00:00+00:00", "changed")
    assert service.get_latest("douyin-pet").as_dict()["status"] == "STALE"
    posts.create_post("douyin-pet", {"title": "新作品", "views": 100})
    fresh = service.diagnose("douyin-pet")
    assert fresh.id != old.id
    assert fresh.as_dict()["status"] == "COMPLETED"


def test_confidence_copy_and_missing_field_explanations():
    from easel.social_operator.models import Platform
    assert confidence_level(30, 100, 1, 1) == "HIGH"
    assert confidence_level(30, 100, 1, 0) == "MEDIUM"
    assert confidence_level(2, 20, 0.1, 0) == "LOW"
    assert "较可靠" in AccountIntelligenceEngine._confidence_copy("HIGH", {"coverage": {}})
    assert "只能作为参考" in AccountIntelligenceEngine._confidence_copy("MEDIUM", {"coverage": {"content_type": 0}})
    assert "初步参考" in AccountIntelligenceEngine._confidence_copy("LOW", {"coverage": {}})
    gaps = AccountIntelligenceEngine._data_gaps([
        {"publish_time": None, "content_type": None, "views": None, "duration": None,
         "subjects": [], "content_source": "UNKNOWN", "hook_type": None},
    ], Platform.DOUYIN)
    assert {gap["label"] for gap in gaps} == {"发布时间", "内容类型", "播放/曝光", "视频时长", "出镜主体", "真实拍摄 / AI 视频", "开场方式"}


def test_official_snapshot_repair_archives_legacy_scan_and_keeps_82_canonical(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    # Build a small official+legacy fixture with a repeated scan row.
    official = posts.create_post("douyin-pet", {
        "title": "猫咪日常", "publish_time": "2026-01-01", "views": 100, "likes": 5,
    })
    with repo._connect() as conn:
        conn.execute("UPDATE historical_posts SET data_source = 'DOUYIN_OFFICIAL_EXPORT' WHERE id = ?", (official.id,))
        for index, title in enumerate(("猫咪日常 编辑作品 设置权限 作品置顶 删除作品", "猫 咪 日 常")):
            conn.execute(
                "INSERT INTO historical_posts (id, account_id, platform, title, content_source, data_source, "
                "source_presence, created_at, updated_at) VALUES (?, 'douyin-pet', 'douyin', ?, 'UNKNOWN', "
                "'DOUYIN_CREATOR_CENTER', 'MISSING', ?, ?)",
                (f"legacy-{index}", title, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
            )
    manager = SnapshotReconciliationManager(repo)
    preview = manager.preview_repair("douyin-pet")
    assert preview["estimated_unique_count"] == 1
    assert preview["auto_merge_count"] == 2
    assert preview["manual_review_count"] == 0
    result = manager.confirm_repair("douyin-pet", preview["preview_id"])
    assert result["archived_duplicate_count"] == 2
    assert result["canonical_count"] == 1
    assert repo.get_post("douyin-pet", official.id)["data_source"] == "DOUYIN_OFFICIAL_EXPORT"
    archived_titles = [json.loads(row[0])["title"] for row in repo._connect().execute(
        "SELECT payload_json FROM historical_post_archive WHERE account_id='douyin-pet'")]
    assert all("编辑作品" not in title and "设置权限" not in title for title in archived_titles)


def test_batch_classification_rejects_cross_account_post_ids(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    xhs = posts.create_post("xhs-developer", {"title": "开发笔记"})
    try:
        posts.classify_posts("douyin-pet", [xhs.id], {"content_type": "单猫日常"})
    except LookupError:
        pass
    else:
        raise AssertionError("cross-account batch classification must be rejected")


def test_repaired_82_post_dataset_is_the_diagnosis_sample(tmp_path):
    repo = make_repo(tmp_path)
    service = HistoricalPostService(repo)
    official_ids = []
    for index in range(82):
        post = service.create_post("douyin-pet", {
            "title": f"官方作品 {index}", "publish_time": f"2026-08-{(index % 28) + 1:02d}T12:00:00",
            "views": 300 + index * 11, "likes": index % 31, "comments": index % 7,
            "favorites": index % 12, "shares": index % 4,
        })
        official_ids.append(post.id)
    with repo._connect() as conn:
        conn.execute("UPDATE historical_posts SET data_source='DOUYIN_OFFICIAL_EXPORT' WHERE account_id='douyin-pet'")
        legacy_rows = []
        for index in range(202):
            title_index = index % 82
            title = f"官方作品 {title_index} 编辑作品 设置权限 取消置顶 删除作品" if index % 2 else f"官方 作品 {title_index}"
            legacy_rows.append((f"legacy-{index}", title, "2026-08-01T00:00:00+00:00"))
        conn.executemany(
            "INSERT INTO historical_posts (id, account_id, platform, title, content_source, data_source, "
            "source_presence, created_at, updated_at) VALUES (?, 'douyin-pet', 'douyin', ?, 'UNKNOWN', "
            "'DOUYIN_CREATOR_CENTER', 'MISSING', ?, ?)",
            [(row_id, title, created, created) for row_id, title, created in legacy_rows],
        )
    manager = SnapshotReconciliationManager(repo)
    preview = manager.preview_repair("douyin-pet")
    assert preview["database_current_count"] == 284
    assert preview["estimated_unique_count"] == 82
    assert preview["auto_merge_count"] == 202
    assert preview["manual_review_count"] == 0
    manager.confirm_repair("douyin-pet", preview["preview_id"])
    report = AccountDiagnosisService(repo).diagnose("douyin-pet").as_dict()
    assert repo.count_posts("douyin-pet") == 82
    assert report["record_counts"]["archived_legacy_count"] == 202
    assert report["record_counts"]["diagnosis_sample_count"] == 82
    assert len({item["id"] for item in report["top_posts"]}) == len(report["top_posts"])
    assert len({item["id"] for item in report["low_posts"]}) == len(report["low_posts"])


def test_batch_classification_api_updates_one_account_only(tmp_path):
    repo = make_repo(tmp_path)
    accounts = OperatorAccountService(repo)
    posts = HistoricalPostService(repo)
    douyin_post = posts.create_post("douyin-pet", {"title": "需要分类"})
    xhs_post = posts.create_post("xhs-developer", {"title": "XHS 内容"})
    app.dependency_overrides[get_historical_services] = lambda: HistoricalServices(
        accounts, posts, HistoricalImportManager(posts, repo),
    )
    try:
        local = "http://127.0.0.1:7860"
        with TestClient(app, base_url=local, client=("127.0.0.1", 51237), headers={"Origin": local}) as client:
            response = client.patch("/api/operator/accounts/douyin-pet/posts/batch-classify", json={
                "post_ids": [douyin_post.id], "content_source": "REAL", "content_type": "双猫互动",
                "subjects": ["缅因", "布偶"],
            })
            assert response.status_code == 200, response.text
            assert response.json()["updated_count"] == 1
            updated = client.get(f"/api/operator/accounts/douyin-pet/posts/{douyin_post.id}").json()
            assert updated["content_type"] == "双猫互动"
            assert updated["subjects"] == ["缅因", "布偶"]
            cross_account = client.patch("/api/operator/accounts/douyin-pet/posts/batch-classify", json={
                "post_ids": [xhs_post.id], "content_type": "双猫互动",
            })
            assert cross_account.status_code == 404
    finally:
        app.dependency_overrides.pop(get_historical_services, None)
