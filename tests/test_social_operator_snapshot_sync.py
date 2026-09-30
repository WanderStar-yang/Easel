from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from easel.social_operator.diagnosis import AccountDiagnosisService, UnavailableExplainer
from easel.social_operator.historical import HistoricalPostService, normalize_post
from easel.social_operator.historical_sync import HistoricalSyncSessionManager
from easel.social_operator.models import Platform
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from easel.social_operator.snapshot_sync import SnapshotReconciliationManager


@pytest.fixture
def context(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "operator.sqlite3")
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    snapshots = SnapshotReconciliationManager(repository)
    sessions = HistoricalSyncSessionManager(repository)
    return repository, accounts, posts, snapshots, sessions


def record(post_id: str, title: str, *, date: str = "2025年11月11日 09:46", **values):
    return {"platform_post_id": post_id, "title": title, "publish_time_raw": date,
            "views": 100, "likes": 5, "comments": 1, "favorites": 2, "shares": 0, **values}


def apply_snapshot(context, rows, *, raw=None, expected=None):
    repository, _, _, snapshots, _ = context
    summary = snapshots.preview_snapshot(
        "douyin-pet", rows, raw_count=len(rows) if raw is None else raw,
        scan_duplicate_count=0, pages_scanned=1, expected_count=expected if expected is not None else len(rows),
        scan_complete=True,
    )
    assert summary["can_confirm"] is True
    result = snapshots.confirm("douyin-pet", summary["preview_id"])
    return summary, result


def test_snapshot_repeated_sync_is_idempotent_updates_zero_and_keeps_null(context):
    _, _, posts, _, _ = context
    rows = [record(f"id-{i}", f"作品{i}") for i in range(83)]
    first, first_result = apply_snapshot(context, rows)
    assert first["platform_unique_count"] == 83
    assert first_result["canonical_count"] == 83
    stable_ids = {post.platform_post_id: post.id for post in posts.list_posts("douyin-pet", limit=500)}

    second_rows = [dict(row) for row in rows]
    second_rows[0].update(views=0, likes=None)
    second, second_result = apply_snapshot(context, second_rows)
    assert second["insert_count"] == 0 and second["update_count"] == 83
    assert second_result["canonical_count"] == 83
    updated = posts.get_post("douyin-pet", stable_ids["id-0"])
    assert updated.views == 0 and updated.likes == 5
    assert {post.platform_post_id: post.id for post in posts.list_posts("douyin-pet", limit=500)} == stable_ids
    assert posts.list_posts("xhs-developer") == []

    AccountDiagnosisService(context[0], explainer=UnavailableExplainer()).diagnose("douyin-pet")
    unchanged, unchanged_result = apply_snapshot(context, second_rows)
    assert unchanged["insert_count"] == 0 and unchanged["update_count"] == 83
    assert unchanged_result["diagnosis_stale"] is False
    assert context[0].get_latest_diagnosis("douyin-pet")["status"] == "CURRENT"


def test_snapshot_inserts_new_posts_and_marks_missing_without_deleting(context):
    _, _, posts, _, _ = context
    original = [record(f"id-{i}", f"作品{i}") for i in range(5)]
    apply_snapshot(context, original)
    new = [*original[:4], *(record(f"new-{i}", f"新作品{i}") for i in range(3))]
    summary, result = apply_snapshot(context, new)
    assert summary["insert_count"] == 3
    assert summary["platform_missing_count"] == 1
    assert result["canonical_count"] == 8
    missing = next(post for post in posts.list_posts("douyin-pet", limit=100) if post.platform_post_id == "id-4")
    assert missing.source_presence == "MISSING" and missing.missing_since
    assert posts.get_post("douyin-pet", missing.id).id == missing.id


def test_raw_120_to_unique_83_is_previewed_before_any_write(context):
    _, _, posts, snapshots, _ = context
    unique = [record(f"id-{i}", f"作品{i}") for i in range(83)]
    raw_rows = [*unique, *unique[:37]]
    preview = snapshots.preview_snapshot("douyin-pet", raw_rows, raw_count=120, scan_duplicate_count=37,
                                         pages_scanned=3, expected_count=83, scan_complete=True)
    assert preview["raw_observation_count"] == 120
    assert preview["platform_unique_count"] == 83
    assert preview["scan_duplicate_count"] == 37
    assert posts.repository.count_posts("douyin-pet") == 0


def test_repair_202_legacy_rows_to_83_archives_and_remaps_references(context):
    repository, _, posts, snapshots, _ = context
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    legacy_rows = []
    for index in range(83):
        base_title = f"猫咪作品 {index}"
        legacy_rows.append({"title": base_title, "views": 10 + index, "likes": 2,
                            "data_source": "DOUYIN_CREATOR_CENTER",
                            "source_updated_at": (now + timedelta(seconds=1)).isoformat()})
    for duplicate_index in range(119):
        index = duplicate_index % 83
        base_title = f"猫咪作品 {index}"
        decorated_title = base_title + " 编辑作品 设置权限 作品置顶 删除作品"
        legacy_rows.append({"title": decorated_title, "views": 1000 + duplicate_index, "likes": 0,
                            "data_source": "DOUYIN_CREATOR_CENTER",
                            "source_updated_at": (now + timedelta(seconds=duplicate_index + 2)).isoformat()})
    inserted, duplicates = repository.create_posts(
        [(f"post-{index}", {**normalize_post(row, Platform.DOUYIN), "account_id": "douyin-pet",
                            "data_source": row["data_source"], "source_updated_at": row["source_updated_at"]})
         for index, row in enumerate(legacy_rows)], now.isoformat(),
    )
    assert len(inserted) == 202 and not duplicates
    old_ids = [row["id"] for row in repository.list_posts("douyin-pet", limit=500)]
    report = {"input_evidence": {"historical_post_ids": old_ids,
                                  "historical_post_versions": [{"id": post_id, "updated_at": now.isoformat()} for post_id in old_ids]},
              "top_posts": [{"id": old_ids[0]}]}
    repository.save_diagnosis("diagnosis-1", "douyin-pet", "test", json.dumps(report), now.isoformat())

    preview = snapshots.preview_repair("douyin-pet")
    assert preview["database_current_count"] == 202
    assert preview["canonical_count_after_repair"] == 83
    assert preview["duplicate_count"] == 119
    assert posts.repository.count_posts("douyin-pet") == 202
    result = snapshots.confirm_repair("douyin-pet", preview["preview_id"])
    assert result["archived_duplicate_count"] == 119 and result["canonical_count"] == 83
    assert result["reference_remap_count"] == 119 and result["diagnosis_stale"] is True
    assert repository._connect().execute("SELECT COUNT(*) FROM historical_post_archive").fetchone()[0] == 119
    latest = repository.get_latest_diagnosis("douyin-pet")
    assert latest["status"] == "STALE"
    remapped = latest["report"]["input_evidence"]["historical_post_ids"]
    assert len(remapped) == 83 and len(set(remapped)) == 83
    assert all("编辑作品" not in post.title for post in posts.list_posts("douyin-pet", limit=100))


def test_snapshot_backfills_chinese_publish_time_and_null_does_not_erase_metrics(context):
    repository, _, posts, snapshots, _ = context
    now = datetime(2026, 9, 29, tzinfo=timezone.utc).isoformat()
    legacy = normalize_post({"title": "回填作品 编辑作品 设置权限 作品置顶 删除作品", "views": 99, "likes": 4}, Platform.DOUYIN)
    legacy.update(account_id="douyin-pet", data_source="DOUYIN_CREATOR_CENTER", source_updated_at=now)
    repository.create_posts([("legacy-post", legacy)], now)
    incoming = record("platform-9", "回填作品", views=None, likes=None)
    preview, result = apply_snapshot(context, [incoming])
    assert preview["publish_time_backfill_count"] == 1
    post = posts.get_post("douyin-pet", "legacy-post")
    assert post.id == "legacy-post"
    assert post.publish_time == "2025-11-11T09:46:00+08:00"
    assert post.publish_time_raw == "2025年11月11日 09:46"
    assert post.views == 99 and post.likes == 4
    assert post.platform_post_id == "platform-9"
    assert result["canonical_count"] == 1
    assert normalize_post({"title": "time", "publish_time_raw": "2025年11月11日 09:46"}, Platform.DOUYIN)["publish_time"] == "2025-11-11T09:46:00+08:00"


def test_snapshot_preview_requires_complete_count_and_rejects_stale_confirm(context):
    repository, _, posts, snapshots, _ = context
    rows = [record("one", "一号")]
    incomplete = snapshots.preview_snapshot("douyin-pet", rows, raw_count=1, scan_duplicate_count=0,
                                             pages_scanned=1, expected_count=2, scan_complete=True)
    assert incomplete["can_confirm"] is False
    with pytest.raises(ValueError, match="必须完成"):
        snapshots.confirm("douyin-pet", incomplete["preview_id"])
    complete = snapshots.preview_snapshot("douyin-pet", rows, raw_count=1, scan_duplicate_count=0,
                                           pages_scanned=1, expected_count=1, scan_complete=True)
    posts.create_post("douyin-pet", {"title": "并发改动"})
    with pytest.raises(ValueError, match="预览后发生"):
        snapshots.confirm("douyin-pet", complete["preview_id"])


def test_snapshot_updates_mark_previous_diagnosis_stale(context):
    repository, _, posts, _, _ = context
    posts.create_post("douyin-pet", {"title": "旧数据", "publish_time": "2025-01-01", "views": 3})
    diagnosis = AccountDiagnosisService(repository, explainer=UnavailableExplainer()).diagnose("douyin-pet")
    assert diagnosis.as_dict()["status"] == "COMPLETED"
    posts.update_post("douyin-pet", diagnosis.report["input_evidence"]["historical_post_ids"][0], {"views": 4})
    stale = AccountDiagnosisService(repository, explainer=UnavailableExplainer()).get_latest("douyin-pet")
    assert stale.as_dict()["status"] == "STALE"


def test_pause_resume_same_session_deduplicates_revisited_first_page(context):
    _, _, _, _, sessions = context
    url = "https://creator.douyin.com/creator-micro/content/manage"
    session = sessions.create("douyin-pet")
    session_id = session["session_id"]
    first = {"platform_post_id": "seen-1", "title": "一号", "publish_time_raw": "2025年11月11日 09:46"}
    saved = sessions.checkpoint("douyin-pet", session_id, [first], url, page_fingerprint="p1", has_next=True)
    assert saved["unique_count"] == 1
    sessions.control("douyin-pet", session_id, "pause")
    paused = sessions.checkpoint("douyin-pet", session_id, [first], url, page_fingerprint="p1", has_next=True)
    assert paused["status"] == "paused" and paused["unique_count"] == 1
    resumed = sessions.control("douyin-pet", session_id, "resume")
    assert resumed["session_id"] == session_id and resumed["status"] == "resume_requested"
    again = sessions.checkpoint("douyin-pet", session_id, [first], url, page_fingerprint="p1", has_next=True)
    assert again["unique_count"] == 1 and again["raw_observation_count"] == 3
    assert again["duplicate_count"] == 2 and again["seen_post_ids"] == ["seen-1"]
    finished = sessions.checkpoint("douyin-pet", session_id,
                                   [{"platform_post_id": "seen-2", "title": "二号",
                                     "publish_time_raw": "2025年11月12日 09:46"}],
                                   url, page_fingerprint="p2", has_next=False, expected_count=2)
    assert finished["status"] == "scan_completed" and finished["unique_count"] == 2


def test_cross_account_repair_is_rejected(context):
    _, _, _, snapshots, _ = context
    with pytest.raises(ValueError, match="仅适用于抖音"):
        snapshots.preview_repair("xhs-developer")
