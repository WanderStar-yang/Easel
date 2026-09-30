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
    return HistoricalServices(accounts, posts, imports, HistoricalSyncSessionManager(repository))


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
        "platform_post_id", "title", "publish_time", "publish_time_raw", "duration", "views", "likes", "comments",
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
        conn.execute("ALTER TABLE douyin_sync_sessions DROP COLUMN expected_count")
        conn.execute("PRAGMA user_version = 3")
    upgraded = OperatorAccountRepository(db_path)
    OperatorAccountService(upgraded)
    migrated = HistoricalPostService(upgraded).get_post("douyin-pet", post.id)
    assert migrated.title == "迁移前记录" and migrated.views == 27
    assert migrated.data_source == "MANUAL"
    with upgraded._connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        post_columns = {row["name"] for row in conn.execute("PRAGMA table_info(historical_posts)")}
        assert {"publish_time_raw", "source_presence", "missing_since"} <= post_columns
        diagnosis_columns = {row["name"] for row in conn.execute("PRAGMA table_info(account_diagnoses)")}
        assert {"status", "stale_at", "stale_reason"} <= diagnosis_columns
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'douyin_sync_sessions'",
        ).fetchone() is not None
        assert "expected_count" in {
            row["name"] for row in conn.execute("PRAGMA table_info(douyin_sync_sessions)")
        }
        account_columns = {row["name"] for row in conn.execute("PRAGMA table_info(operator_accounts)")}
        assert {"last_sync_at", "last_sync_source", "last_sync_counts_json"} <= account_columns


def test_sync_session_expires_by_account_and_rejects_other_origin(services):
    session = services.sync_sessions.create("douyin-pet")
    assert session["status"] == "extension_unavailable"
    assert session["extension_available"] is False
    connected = services.sync_sessions.report_state(
        "douyin-pet", session["session_id"], "not_logged_in", "请自行登录",
        "https://creator.douyin.com/creator-micro/content/manage",
    )
    assert connected["status"] == "not_logged_in"
    assert connected["extension_available"] is True
    assert connected["message"] == "请自行登录" and connected["last_seen_at"]
    with pytest.raises(LookupError):
        services.sync_sessions.get("xhs-developer", session["session_id"])
    with pytest.raises(PermissionError):
        services.sync_sessions.attach_preview(
            "douyin-pet", session["session_id"], "p1", {}, "https://evil.example/creator.douyin.com",
        )


def test_sync_checkpoints_persist_across_manager_restart_and_deduplicate_in_two_stages(services):
    session = services.sync_sessions.create("douyin-pet")
    session_id = session["session_id"]
    creator_url = "https://creator.douyin.com/creator-micro/content/manage"
    first = services.sync_sessions.checkpoint("douyin-pet", session_id, [{
        "title": "  Cat　story ", "publish_time": "2025/01/02", "views": 10,
    }], creator_url, page_fingerprint="page-1", has_next=True, next_page_hint="page-2")
    assert first["raw_observation_count"] == 1 and first["unique_count"] == 1

    # Construct a new manager as if the web server restarted. The account-bound
    # session and first page are loaded from the existing SQLite database.
    restarted = HistoricalSyncSessionManager(services.posts.repository)
    restored = restarted.get("douyin-pet", session_id)
    assert restored["pages_scanned"] == 1 and restored["has_more"] is True
    second = restarted.checkpoint("douyin-pet", session_id, [{
        "platform_post_id": "aweme-1", "title": "cat story", "publish_time": "2025-01-02", "likes": 2,
    }, {
        "platform_post_id": "aweme-1", "title": "cat story", "publish_time": "2025-01-02", "views": 12,
    }], creator_url, page_fingerprint="page-2", has_next=False)
    assert second["raw_observation_count"] == 3
    assert second["unique_count"] == 1
    assert second["duplicate_count"] == 2
    assert second["pages_scanned"] == 2 and second["status"] == "scan_completed"
    assert restarted.preview_records("douyin-pet", session_id)[0]["platform_post_id"] == "aweme-1"
    with pytest.raises(LookupError):
        restarted.get("xhs-developer", session_id)


def test_sync_control_requests_pause_resume_end_and_cancel(services):
    manager = services.sync_sessions
    session_id = manager.create("douyin-pet")["session_id"]
    assert manager.control("douyin-pet", session_id, "pause")["status"] == "pause_requested"
    assert manager.report_state("douyin-pet", session_id, "paused")["status"] == "paused"
    assert manager.control("douyin-pet", session_id, "resume")["status"] == "resume_requested"
    assert manager.control("douyin-pet", session_id, "cancel")["status"] == "cancelled"
    with pytest.raises(ValueError, match="不能再控制"):
        manager.control("douyin-pet", session_id, "resume")


def test_sync_does_not_mark_complete_below_creator_center_declared_count(services):
    manager = services.sync_sessions
    session_id = manager.create("douyin-pet")["session_id"]
    url = "https://creator.douyin.com/creator-micro/content/manage"
    partial = manager.checkpoint("douyin-pet", session_id, [
        {"platform_post_id": "one", "title": "作品一"},
        {"platform_post_id": "two", "title": "作品二"},
    ], url, page_fingerprint="partial", has_next=False, expected_count=3)
    assert partial["status"] == "paused"
    assert partial["unique_count"] == 2 and partial["has_more"] is True
    assert "共显示 3 条" in partial["message"]
    complete = manager.checkpoint("douyin-pet", session_id, [
        {"platform_post_id": "three", "title": "作品三"},
    ], url, page_fingerprint="recovered", has_next=False, expected_count=3)
    assert complete["status"] == "scan_completed"
    assert complete["unique_count"] == 3 and complete["has_more"] is False


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
        assert start.json()["status"] == "extension_unavailable"
        assert start.json()["extension_available"] is False
        ext_state = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}/extension-state",
            json={"status": "not_logged_in", "message": "请自行扫码登录",
                  "source_url": "https://creator.douyin.com/login"},
        )
        assert ext_state.status_code == 200 and ext_state.json()["status"] == "not_logged_in"
        assert ext_state.json()["extension_available"] is True
        for state in ("extension_available", "creator_tab_not_found", "unsupported_page", "ready_to_scan",
                      "scanning", "scan_completed"):
            ready_state = client.post(
                f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}/extension-state",
                json={"status": state, "message": state,
                      "source_url": "https://creator.douyin.com/creator-micro/content/manage"},
            )
            assert ready_state.status_code == 200 and ready_state.json()["status"] == state
        checkpoint = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}/checkpoint",
            json={"source_url": "https://creator.douyin.com/creator-micro/content/manage",
                  "page_fingerprint": "one-full-page", "has_next": False,
                  "rows": [{"platform_post_id": "api-1", "title": "API 可见作品",
                            "publish_time_raw": "2025年11月11日 09:46", "views": 0, "likes": None}]},
        )
        assert checkpoint.status_code == 200 and checkpoint.json()["status"] == "scan_completed"
        invalid_origin = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}/preview",
            json={"source_url": "https://example.com/", "records": []},
        )
        assert invalid_origin.status_code == 403
        scanned = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}/preview",
            json={"source_url": "https://creator.douyin.com/creator-micro/content/manage", "records": []},
        )
        assert scanned.status_code == 201, scanned.text
        assert scanned.json()["status"] == "preview_ready"
        preview_id = scanned.json()["preview_id"]
        assert client.get("/api/operator/accounts/douyin-pet/posts").json()["total"] == 0
        session_status = client.get(f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session_id}")
        assert session_status.status_code == 200 and session_status.json()["preview_id"] == preview_id
        xhs_start = client.post("/api/operator/accounts/xhs-developer/posts/sync/sessions")
        assert xhs_start.status_code == 409
        confirmed = client.post("/api/operator/accounts/douyin-pet/posts/sync/snapshots/confirm",
                                json={"preview_id": preview_id})
        assert confirmed.status_code == 200 and confirmed.json()["inserted_count"] == 1
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


def test_end_completed_scan_preserves_preview_state_and_partial_scan_is_read_only(services):
    client_ctx = _api(services)
    client = next(client_ctx)
    creator_url = "https://creator.douyin.com/creator-micro/content/manage"
    try:
        complete = client.post("/api/operator/accounts/douyin-pet/posts/sync/sessions").json()
        complete_id = complete["session_id"]
        checkpoint = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{complete_id}/checkpoint",
            json={"source_url": creator_url, "page_fingerprint": "complete", "has_next": False,
                  "rows": [{"platform_post_id": "complete-1", "title": "完整扫描作品"}]},
        )
        assert checkpoint.json()["status"] == "scan_completed"
        ended_complete = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{complete_id}/control",
            json={"action": "end"},
        )
        assert ended_complete.json()["status"] == "scan_completed"
        full_preview = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{complete_id}/preview",
            json={"source_url": creator_url, "records": []},
        )
        assert full_preview.status_code == 201
        assert full_preview.json()["preview"]["snapshot_complete"] is True

        partial = client.post("/api/operator/accounts/douyin-pet/posts/sync/sessions").json()
        partial_id = partial["session_id"]
        partial_checkpoint = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{partial_id}/checkpoint",
            json={"source_url": creator_url, "page_fingerprint": "partial", "has_next": True,
                  "next_page_hint": "下一页", "rows": [{"platform_post_id": "partial-1", "title": "部分扫描作品"}]},
        )
        assert partial_checkpoint.json()["status"] == "scanning"
        paused = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{partial_id}/control",
            json={"action": "pause"},
        )
        assert paused.json()["status"] == "pause_requested"
        saved_pause = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{partial_id}/checkpoint",
            json={"source_url": creator_url, "page_fingerprint": "partial", "has_next": True,
                  "rows": [{"platform_post_id": "partial-1", "title": "部分扫描作品"}]},
        )
        assert saved_pause.json()["status"] == "paused"
        ended_partial = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{partial_id}/control",
            json={"action": "end"},
        )
        assert ended_partial.json()["status"] == "ended"
        partial_preview = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{partial_id}/preview",
            json={"source_url": creator_url, "records": []},
        )
        assert partial_preview.status_code == 201, partial_preview.text
        assert partial_preview.json()["status"] == "preview_ready"
        assert partial_preview.json()["preview"]["snapshot_complete"] is False
        assert partial_preview.json()["preview"]["can_confirm"] is False
        denied = client.post("/api/operator/accounts/douyin-pet/posts/sync/snapshots/confirm",
                             json={"preview_id": partial_preview.json()["preview_id"]})
        assert denied.status_code == 409
        assert client.get("/api/operator/accounts/douyin-pet/posts").json()["total"] == 0
    finally:
        client.close()
        next(client_ctx, None)


def test_chrome_extension_preflight_is_restricted_to_sync_paths(services):
    from web.app import app

    app.dependency_overrides[get_historical_services] = lambda: services
    try:
        client = TestClient(app, base_url="http://127.0.0.1:7860", client=("127.0.0.1", 53112))
        origin = "chrome-extension://" + "a" * 32
        path = "/api/operator/accounts/douyin-pet/posts/sync/sessions/opaque-token/preview"
        state_path = "/api/operator/accounts/douyin-pet/posts/sync/sessions/opaque-token/extension-state"
        checkpoint_path = "/api/operator/accounts/douyin-pet/posts/sync/sessions/opaque-token/checkpoint"
        response = client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        state_response = client.options(state_path, headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert state_response.status_code == 200
        assert state_response.headers["access-control-allow-origin"] == origin
        checkpoint_response = client.options(checkpoint_path, headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert checkpoint_response.status_code == 200
        assert checkpoint_response.headers["access-control-allow-origin"] == origin
        session = services.sync_sessions.create("douyin-pet")
        reported = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session['session_id']}/extension-state",
            headers={"Origin": origin, "Content-Type": "application/json"},
            json={"status": "extension_available", "message": "扩展连接成功"},
        )
        assert reported.status_code == 200 and reported.headers["access-control-allow-origin"] == origin
        assert reported.json()["status"] == "extension_available"
        checkpointed = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session['session_id']}/checkpoint",
            headers={"Origin": origin, "Content-Type": "application/json"},
            json={"source_url": "https://creator.douyin.com/creator-micro/content/manage",
                  "page_fingerprint": "page-1", "rows": [{"platform_post_id": "scan-1", "title": "检查点"}],
                  "has_next": True, "next_page_hint": "page-2"},
        )
        assert checkpointed.status_code == 200 and checkpointed.headers["access-control-allow-origin"] == origin
        assert checkpointed.json()["unique_count"] == 1 and checkpointed.json()["raw_observation_count"] == 1
        final_page = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session['session_id']}/checkpoint",
            headers={"Origin": origin, "Content-Type": "application/json"},
            json={"source_url": "https://creator.douyin.com/creator-micro/content/manage",
                  "page_fingerprint": "page-2", "rows": [{"platform_post_id": "scan-2", "title": "末页作品",
                    "publish_time_raw": "2025年11月12日 09:46"}], "has_next": False},
        )
        assert final_page.status_code == 200 and final_page.json()["status"] == "scan_completed"
        read_session = client.get(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session['session_id']}",
            headers={"Origin": origin},
        )
        assert read_session.status_code == 200 and read_session.headers["access-control-allow-origin"] == origin
        posted = client.post(
            f"/api/operator/accounts/douyin-pet/posts/sync/sessions/{session['session_id']}/preview",
            headers={"Origin": origin, "Content-Type": "application/json"},
            json={"source_url": "https://creator.douyin.com/creator-micro/content/manage",
                  "records": []},
        )
        assert posted.status_code == 201, posted.text
        assert posted.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-origin" not in client.options(
            path, headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        ).headers
    finally:
        app.dependency_overrides.pop(get_historical_services, None)
