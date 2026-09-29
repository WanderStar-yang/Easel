from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from easel.social_operator.data_sources import DouyinCreatorCenterAdapter, DouyinOpenApiAdapter
from easel.social_operator.diagnosis import AccountDiagnosisService, UnavailableExplainer
from easel.social_operator.historical import HistoricalPostService
from easel.social_operator.historical_imports import HistoricalImportManager
from easel.social_operator.historical_sync import HistoricalSyncSessionManager
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from web.routers.historical_posts import HistoricalServices, get_historical_services
from web.routers.operator_diagnosis import get_diagnosis_service


@pytest.fixture
def services(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "operator.sqlite3")
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    imports = HistoricalImportManager(posts, repository)
    return HistoricalServices(accounts, posts, imports, HistoricalSyncSessionManager())


def _api(services):
    from web.app import app

    app.dependency_overrides[get_historical_services] = lambda: services
    try:
        yield TestClient(app, base_url="http://127.0.0.1:7860", client=("127.0.0.1", 53111))
    finally:
        app.dependency_overrides.pop(get_historical_services, None)


def test_creator_center_adapter_keeps_missing_null_and_zero_and_does_not_classify():
    adapted = DouyinCreatorCenterAdapter().adapt([{
        "platform_post_id": "aweme-1", "title": "可见标题", "publish_time": None,
        "play_count": 0, "likes": 0, "comments": None,
    }])[0]
    assert adapted["views"] == 0
    assert adapted["likes"] == 0
    assert adapted["comments"] is None
    assert adapted["publish_time"] is None
    assert set(adapted) == {
        "platform_post_id", "title", "publish_time", "duration", "views", "likes", "comments",
        "favorites", "shares",
    }


def test_open_api_adapter_is_an_honest_unconfigured_placeholder(monkeypatch):
    for key in ("DOUYIN_CLIENT_KEY", "DOUYIN_CLIENT_SECRET", "DOUYIN_VIDEO_PERMISSIONS_GRANTED"):
        monkeypatch.delenv(key, raising=False)
    status = DouyinOpenApiAdapter.configuration_status()
    assert status["configured"] is False
    assert status["implementation_available"] is False
    with pytest.raises(RuntimeError, match="不会伪造"):
        DouyinOpenApiAdapter().adapt([])


def test_sync_preview_is_account_scoped_and_does_not_persist_until_confirm(services):
    session = services.sync_sessions.create("douyin-pet")
    preview_id, summary = services.imports.preview_records(
        "douyin-pet", DouyinCreatorCenterAdapter().adapt([{
            "platform_post_id": "aweme-1", "title": "真实作品", "views": 0,
            "likes": None, "comments": 3,
        }]), source="DOUYIN_CREATOR_CENTER", update_existing=True,
    )
    services.sync_sessions.attach_preview(
        "douyin-pet", session["session_id"], preview_id,
        {"preview_id": preview_id, **summary}, "https://creator.douyin.com/creator-micro/content/manage",
    )
    assert services.posts.list_posts("douyin-pet") == []
    assert services.posts.list_posts("xhs-developer") == []
    result = services.imports.confirm("douyin-pet", preview_id)
    assert result["imported_count"] == 1
    post = services.posts.list_posts("douyin-pet")[0]
    assert post.platform_post_id == "aweme-1"
    assert post.views == 0 and post.likes is None and post.comments == 3
    assert post.data_source == "DOUYIN_CREATOR_CENTER"
    assert post.source_updated_at
    assert services.posts.list_posts("xhs-developer") == []
    status = services.posts.repository.get_sync_status("douyin-pet")
    assert status["last_sync_at"] == result["last_sync_at"]
    assert status["last_sync_source"] == "DOUYIN_CREATOR_CENTER"
    assert status["last_sync_counts"]["inserted_count"] == 1


def test_incremental_sync_updates_platform_id_metrics_and_preserves_user_classification(services):
    original = services.posts.create_post("douyin-pet", {
        "title": "手工补过分类", "publish_time": "2025-03-01", "platform_post_id": "aweme-42",
        "content_type": "双猫互动", "content_source": "REAL", "subjects": ["缅因", "布偶"],
        "tags": ["已人工确认"], "views": 10, "likes": 2, "comments": 1,
    })
    preview_id, summary = services.imports.preview_records(
        "douyin-pet", DouyinCreatorCenterAdapter().adapt([{
            "platform_post_id": "aweme-42", "title": "平台标题更新", "views": 0,
            "likes": 0, "comments": None, "favorites": 5,
        }, {
            "platform_post_id": "aweme-43", "title": "新作品", "publish_time": "2025-03-02",
            "views": 18, "likes": 1,
        }]), source="DOUYIN_CREATOR_CENTER", update_existing=True,
    )
    assert summary["update_count"] == 1 and summary["importable_count"] == 1
    assert len(services.posts.list_posts("douyin-pet")) == 1  # preview is read-only
    result = services.imports.confirm("douyin-pet", preview_id)
    assert result["updated_count"] == 1 and result["imported_count"] == 1
    rows = services.posts.list_posts("douyin-pet")
    existing = next(row for row in rows if row.id == original.id)
    assert existing.views == 0 and existing.likes == 0 and existing.comments == 1
    assert existing.favorites == 5
    assert existing.title == "手工补过分类"
    assert existing.content_type == "双猫互动" and existing.content_source.value == "REAL"
    assert existing.subjects == ["缅因", "布偶"] and existing.tags == ["已人工确认"]
    assert {row.platform_post_id for row in rows} == {"aweme-42", "aweme-43"}


def test_sync_without_platform_id_uses_phase2_duplicate_rule_and_skips_without_merge(services):
    original = services.posts.create_post("douyin-pet", {
        "title": "无平台 ID 的作品", "publish_time": "2025-04-01", "views": 10,
    })
    preview_id, summary = services.imports.preview_records(
        "douyin-pet", [{"title": "无平台 ID 的作品", "publish_time": "2025-04-01", "views": 99}],
        source="DOUYIN_CREATOR_CENTER", update_existing=True,
    )
    assert summary["duplicate_count"] == 1
    result = services.imports.confirm("douyin-pet", preview_id)
    assert result["imported_count"] == 0 and result["updated_count"] == 0
    assert services.posts.get_post("douyin-pet", original.id).views == 10


def test_repeated_sync_is_idempotent_and_only_reports_updates(services):
    record = {"platform_post_id": "repeat-1", "title": "可重复扫描作品", "views": 12, "likes": 2}
    for expected_new, expected_update in ((1, 0), (0, 1)):
        preview_id, _ = services.imports.preview_records(
            "douyin-pet", DouyinCreatorCenterAdapter().adapt([record]),
            source="DOUYIN_CREATOR_CENTER", update_existing=True,
        )
        result = services.imports.confirm("douyin-pet", preview_id)
        assert result["imported_count"] == expected_new
        assert result["updated_count"] == expected_update
    assert len(services.posts.list_posts("douyin-pet")) == 1
    assert services.posts.repository.get_sync_status("douyin-pet")["last_sync_counts"]["updated_count"] == 1


def test_manual_and_file_sources_have_source_metadata(services):
    manual = services.posts.create_post("douyin-pet", {"title": "手工录入"})
    assert manual.data_source == "MANUAL" and manual.source_updated_at is None
    preview_id, _ = services.imports.preview("douyin-pet", "one.csv", "标题,播放量\n文件导入,20\n".encode())
    services.imports.confirm("douyin-pet", preview_id)
    imported = next(row for row in services.posts.list_posts("douyin-pet") if row.title == "文件导入")
    assert imported.data_source == "FILE_IMPORT" and imported.source_updated_at


def test_phase3_sqlite_schema_migrates_additive_sync_metadata(tmp_path):
    db_path = tmp_path / "operator.sqlite3"
    repository = OperatorAccountRepository(db_path)
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    post = posts.create_post("douyin-pet", {"title": "迁移前记录", "views": 27})
    with repository._connect() as conn:
        for table, columns in {
            "historical_posts": ("source_updated_at", "data_source"),
            "operator_accounts": ("last_sync_counts_json", "last_sync_source", "last_sync_at"),
        }.items():
            for column in columns:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.execute("PRAGMA user_version = 3")
    upgraded = OperatorAccountRepository(db_path)
    OperatorAccountService(upgraded)
    migrated = HistoricalPostService(upgraded).get_post("douyin-pet", post.id)
    assert migrated.title == "迁移前记录" and migrated.views == 27
    assert migrated.data_source == "MANUAL"
    with upgraded._connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        account_columns = {row["name"] for row in conn.execute("PRAGMA table_info(operator_accounts)")}
        assert {"last_sync_at", "last_sync_source", "last_sync_counts_json"} <= account_columns


def test_sync_session_expires_by_account_and_rejects_other_origin(services):
    session = services.sync_sessions.create("douyin-pet")
    with pytest.raises(LookupError):
        services.sync_sessions.get("xhs-developer", session["session_id"])
    with pytest.raises(PermissionError):
        services.sync_sessions.attach_preview(
            "douyin-pet", session["session_id"], "p1", {}, "https://evil.example/creator.douyin.com",
        )


def test_sync_api_preview_confirm_status_diagnosis_and_platform_isolation(services):
    client_ctx = _api(services)
    client = next(client_ctx)
    from easel.social_operator.diagnosis import AccountDiagnosisService, UnavailableExplainer
    from easel.social_operator.repository import OperatorAccountRepository

    diagnosis = AccountDiagnosisService(services.posts.repository, explainer=UnavailableExplainer())
    from web.routers.operator_diagnosis import get_diagnosis_service
    from web.app import app
    app.dependency_overrides[get_diagnosis_service] = lambda: diagnosis
    try:
        start = client.post("/api/operator/accounts/douyin-pet/posts/sync/sessions")
        assert start.status_code == 201, start.text
        session_id = start.json()["session_id"]
        invalid_origin = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}/preview",
            json={"source_url": "https://example.com/", "records": []},
        )
        assert invalid_origin.status_code == 403
        scanned = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}/preview",
            json={"source_url": "https://creator.douyin.com/creator-micro/content/manage", "records": [
                {"platform_post_id": "api-1", "title": "API 可见作品", "views": 0, "likes": None},
            ]},
        )
        assert scanned.status_code == 201, scanned.text
        assert scanned.json()["status"] == "preview_ready"
        preview_id = scanned.json()["preview_id"]
        assert client.get("/api/operator/accounts/douyin-pet/posts").json()["total"] == 0
        session_status = client.get(f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}")
        assert session_status.status_code == 200 and session_status.json()["preview_id"] == preview_id
        xhs_start = client.post("/api/operator/accounts/xhs-developer/posts/sync/sessions")
        assert xhs_start.status_code == 409
        confirmed = client.post("/api/operator/accounts/douyin-pet/posts/imports/confirm",
                                json={"preview_id": preview_id})
        assert confirmed.status_code == 200 and confirmed.json()["imported_count"] == 1
        posts = client.get("/api/operator/accounts/douyin-pet/posts").json()
        assert posts["total"] == 1 and posts["items"][0]["data_source"] == "DOUYIN_CREATOR_CENTER"
        assert client.get("/api/operator/accounts/xhs-developer/posts").json()["total"] == 0
        report = client.post("/api/operator/accounts/douyin-pet/diagnosis")
        assert report.status_code == 200
        assert report.json()["input_evidence"]["sample_size"] == 1
        assert client.get("/api/operator/accounts/douyin-pet/posts/sync/status").json()["last_sync_at"]
        assert client.get("/api/operator/accounts/douyin-pet/posts/sync/openapi-status").status_code == 200
        # The original Easel platform-account API remains registered.
        assert client.get("/api/accounts").status_code == 200
    finally:
        app.dependency_overrides.pop(get_diagnosis_service, None)
        client.close()
        next(client_ctx, None)


def test_chrome_extension_preflight_is_restricted_to_sync_preview_path(services):
    from web.app import app

    app.dependency_overrides[get_historical_services] = lambda: services
    try:
        client = TestClient(app, base_url="http://127.0.0.1:7860", client=("127.0.0.1", 53112))
        origin = "chrome-extension://" + "a" * 32
        path = "/api/operator/accounts/douyin-pet/posts/sync/sessions/opaque-token/preview"
        response = client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        session = services.sync_sessions.create("douyin-pet")
        posted = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session['session_id']}/preview",
            headers={"Origin": origin, "Content-Type": "application/json"},
            json={"source_url": "https://creator.douyin.com/creator-micro/content/manage",
                  "records": [{"title": "扩展已主动扫描", "views": 0}]},
        )
        assert posted.status_code == 201, posted.text
        assert posted.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-origin" not in client.options(
            path, headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        ).headers
    finally:
        app.dependency_overrides.pop(get_historical_services, None)
