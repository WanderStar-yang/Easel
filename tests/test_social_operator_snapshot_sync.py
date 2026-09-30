from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from easel.social_operator.diagnosis import AccountDiagnosisService, UnavailableExplainer
from easel.social_operator.historical import HistoricalPostService, normalize_post
from easel.social_operator.historical_imports import HistoricalImportManager
from easel.social_operator.models import Platform
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from easel.social_operator.snapshot_reconciliation import SnapshotReconciliationManager
from web.app import app
from web.routers.historical_posts import HistoricalServices, get_historical_services


@pytest.fixture
def context(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "operator.sqlite3")
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    services = HistoricalServices(accounts, posts, HistoricalImportManager(posts, repository),
                                  SnapshotReconciliationManager(repository))
    app.dependency_overrides[get_historical_services] = lambda: services
    yield repository, accounts, posts, services.snapshots, services
    app.dependency_overrides.pop(get_historical_services, None)


def export_xlsx(rows: list[dict]) -> bytes:
    output = io.BytesIO()
    pd.DataFrame(rows).to_excel(output, index=False, engine="openpyxl")
    return output.getvalue()


def upload(rows: list[dict], account="douyin-pet"):
    return TestClient(app, base_url="http://localhost:7860", headers={"Origin": "http://localhost:7860"}).post(f"/api/operator/accounts/{account}/posts/imports/preview",
        files={"file": ("作品列表导出.xlsx", export_xlsx(rows),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def confirm_snapshot(account, preview_id):
    return TestClient(app, base_url="http://localhost:7860", headers={"Origin": "http://localhost:7860"}).post(f"/api/operator/accounts/{account}/posts/imports/snapshot-confirm",
                                json={"preview_id": preview_id})


def official_row(title="双猫日常", post_id="dy-1", **values):
    return {"作品名称": title, "发布时间": "2025-11-11 09:46:00", "作品 ID": post_id,
            "体裁": "横屏视频", "播放量": 1200, "点赞量": 80, "评论量": 12,
            "收藏量": 20, "分享量": 3, "粉丝增量": 4, "审核状态": "已通过", **values}


def test_real_format_headers_mapping_unknown_columns_and_values(context):
    response = upload([official_row()])
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["detected_platform"] == "抖音创作者中心"
    assert preview["source"] == "DOUYIN_OFFICIAL_EXPORT"
    assert preview["file_record_count"] == 1 and preview["error_count"] == 0
    row = preview["rows"][0]["record"]
    assert row["title"] == "双猫日常" and row["platform_post_id"] == "dy-1"
    assert row["content_type_raw"] == "横屏视频"
    assert row["publish_time"].startswith("2025-11-11T09:46:00")
    assert tuple(row[key] for key in ("views", "likes", "comments", "favorites", "shares", "followers_gain")) == (1200, 80, 12, 20, 3, 4)
    assert "审核状态" in preview["unsupported_columns"] and preview["can_confirm"] is True


def test_snapshot_reupload_updates_metrics_zero_keeps_null_and_stales_diagnosis(context):
    repository, _, posts, _, _ = context
    first = upload([official_row()]).json()
    assert confirm_snapshot("douyin-pet", first["preview_id"]).status_code == 200
    saved = posts.list_posts("douyin-pet", limit=20)[0]
    AccountDiagnosisService(repository, explainer=UnavailableExplainer()).diagnose("douyin-pet")
    unchanged = upload([official_row()]).json()
    unchanged_result = confirm_snapshot("douyin-pet", unchanged["preview_id"]).json()
    assert unchanged_result["diagnosis_stale"] is True
    AccountDiagnosisService(repository, explainer=UnavailableExplainer()).diagnose("douyin-pet")
    second = upload([official_row(**{"播放量": 0, "点赞量": None, "评论量": None})]).json()
    assert second["insert_count"] == 0 and second["update_count"] == 1
    result = confirm_snapshot("douyin-pet", second["preview_id"]).json()
    updated = posts.get_post("douyin-pet", saved.id)
    assert result["diagnosis_stale"] is True
    assert updated.views == 0 and updated.likes == 80 and updated.comments == 12
    assert updated.data_source == "DOUYIN_OFFICIAL_EXPORT"
    assert posts.repository.get_latest_diagnosis("douyin-pet")["status"] == "STALE"


def test_duplicate_upload_is_idempotent_and_account_scoped(context):
    _, _, posts, _, _ = context
    repeated = upload([official_row(), official_row()]).json()
    assert repeated["file_record_count"] == 2 and repeated["platform_unique_count"] == 1
    assert repeated["duplicate_count"] == 1 and repeated["insert_count"] == 1
    assert confirm_snapshot("douyin-pet", repeated["preview_id"]).status_code == 200
    second = upload([official_row()]).json()
    assert second["insert_count"] == 0 and second["update_count"] == 1
    confirm_snapshot("douyin-pet", second["preview_id"])
    assert posts.repository.count_posts("douyin-pet") == 1
    assert posts.repository.count_posts("xhs-developer") == 0
    assert posts.list_posts("xhs-developer") == []


def test_missing_publish_time_is_warning_not_error_and_no_now_substitution(context):
    row = official_row()
    row.pop("发布时间")
    row.pop("作品 ID")
    preview = upload([row]).json()
    assert preview["error_count"] == 0 and preview["can_confirm"] is True
    assert any("导出文件未提供" in warning for warning in preview["warnings"])
    assert preview["rows"][0]["record"]["publish_time"] is None
    assert preview["identity_confidence"] == "low"


def test_bad_title_and_number_are_row_errors_unknown_column_does_not_fail_file(context):
    response = upload([official_row(title="", **{"点赞量": "not-a-number"})])
    assert response.status_code == 200
    preview = response.json()
    assert preview["error_count"] == 1 and preview["can_confirm"] is False
    assert "审核状态" in preview["unsupported_columns"]
    assert {"title", "likes"}.issubset(preview["errors"][0]["errors"])


def test_official_export_parser_rejects_other_account(context):
    response = upload([official_row()], account="xhs-developer")
    assert response.status_code == 422


def test_repair_preview_separates_automatic_and_manual_duplicates(context):
    repository, _, posts, snapshots, _ = context
    now = datetime.now(timezone.utc).isoformat()
    rows = [("one", "FILE_IMPORT", "stable", "2025-11-01", None), ("two", "FILE_IMPORT", "stable", "2025-11-01", None),
            ("legacy1", "DOUYIN_CREATOR_CENTER", "legacy title", None, None),
            ("legacy2", "DOUYIN_CREATOR_CENTER", "legacy title 编辑作品 设置权限 作品置顶 删除作品", None, None)]
    for post_id, source, title, publish_time, platform_id in rows:
        values = normalize_post({"title": title, "publish_time": publish_time, "platform_post_id": platform_id}, Platform.DOUYIN)
        values.update(account_id="douyin-pet", data_source=source, source_updated_at=now)
        with repository._connect() as conn:
            repository._write_post(conn, "douyin-pet", post_id, values, now, insert=True)
    preview = snapshots.preview_repair("douyin-pet")
    assert preview["database_current_count"] == 4
    assert preview["estimated_unique_count"] == 2
    assert preview["auto_merge_count"] == 1 and preview["manual_review_count"] == 1
    result = snapshots.confirm_repair("douyin-pet", preview["preview_id"],
                                      [preview["manual_review_groups"][0]["group_id"]])
    assert result["archived_duplicate_count"] == 2 and result["manual_review_confirmed"] == 1
    assert posts.repository.count_posts("douyin-pet") == 2


def test_duplicate_repair_marks_existing_diagnosis_stale(context):
    repository, _, _, snapshots, _ = context
    now = datetime.now(timezone.utc).isoformat()
    for post_id in ("repair-a", "repair-b"):
        values = normalize_post({"title": "重复作品", "publish_time": "2025-11-01"}, Platform.DOUYIN)
        values.update(account_id="douyin-pet", data_source="DOUYIN_CREATOR_CENTER", source_updated_at=now)
        with repository._connect() as conn:
            repository._write_post(conn, "douyin-pet", post_id, values, now, insert=True)
    AccountDiagnosisService(repository, explainer=UnavailableExplainer()).diagnose("douyin-pet")
    preview = snapshots.preview_repair("douyin-pet")
    result = snapshots.confirm_repair("douyin-pet", preview["preview_id"])
    assert result["diagnosis_stale"] is True
    assert repository.get_latest_diagnosis("douyin-pet")["status"] == "STALE"


def test_retired_browser_sync_runtime_is_unreferenced():
    from pathlib import Path
    assert not Path("easel/social_operator/historical_sync.py").exists()
    assert not Path("browser-helpers/douyin-sync").exists()
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any("/posts/sync/" in route for route in paths)
    assert "/api/accounts" in paths
    assert "/api/publish/{platform}" in paths


def test_invalid_publish_time_is_row_error(context):
    preview = upload([official_row(**{"发布时间": "not-a-date"})]).json()
    assert preview["error_count"] == 1 and preview["can_confirm"] is False
    assert "publish_time" in preview["errors"][0]["errors"]


def test_empty_csv_can_be_previewed_without_writing(context):
    client = TestClient(app, base_url="http://localhost:7860", headers={"Origin": "http://localhost:7860"})
    response = client.post("/api/operator/accounts/douyin-pet/posts/imports/preview",
                           files={"file": ("empty.csv", b"", "text/csv")})
    assert response.status_code == 200, response.text
    assert response.json()["total_rows"] == 0


def test_confirmed_snapshot_survives_repository_restart(context):
    repository, _, _, _, _ = context
    preview = upload([official_row()]).json()
    result = confirm_snapshot("douyin-pet", preview["preview_id"])
    assert result.status_code == 200, result.text
    restarted = OperatorAccountRepository(repository.db_path)
    persisted = HistoricalPostService(restarted).list_posts("douyin-pet", limit=10)
    assert len(persisted) == 1
    assert persisted[0].data_source == "DOUYIN_OFFICIAL_EXPORT"
    assert persisted[0].platform_post_id == "dy-1"


def test_low_confidence_fingerprint_is_warned_but_repeat_upload_updates_same_record(context):
    _, _, posts, _, _ = context
    row = official_row()
    row.pop("作品 ID")
    row.pop("发布时间")
    first = upload([row]).json()
    assert first["identity_confidence"] == "low"
    assert any("置信度较低" in warning for warning in first["warnings"])
    confirm_snapshot("douyin-pet", first["preview_id"])
    second = upload([row]).json()
    assert second["insert_count"] == 0 and second["update_count"] == 1
    confirm_snapshot("douyin-pet", second["preview_id"])
    assert posts.repository.count_posts("douyin-pet") == 1


def test_csv_with_official_headers_remains_generic_import(context):
    client = TestClient(app, base_url="http://localhost:7860", headers={"Origin": "http://localhost:7860"})
    response = client.post("/api/operator/accounts/douyin-pet/posts/imports/preview",
        files={"file": ("作品列表.csv", "作品名称,点赞量\n猫咪作品,12\n".encode(), "text/csv")})
    assert response.status_code == 200, response.text
    assert response.json().get("preview_kind") != "snapshot"
