from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from easel.social_operator.content_calendar import OperatorContentCalendarService
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.weekly_review import WeeklyReviewService
from web.routers.operator_calendar import get_service, router


def _setup(tmp_path):
    repo = OperatorAccountRepository(tmp_path / "operator-calendar.sqlite3")
    repo.initialize()
    now = "2026-10-01T00:00:00+00:00"
    repo.seed_defaults(now)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("UPDATE operator_accounts SET status='ACTIVE', diagnosis_completed_at=? WHERE id='douyin-pet'", (now,))
        conn.execute("INSERT INTO strategy_recommendations "
                     "(id, account_id, version, generated_at, status, recommendation_json) "
                     "VALUES ('calendar-rec', 'douyin-pet', 1, ?, 'CURRENT', '{}')", (now,))
        conn.execute("INSERT INTO operator_active_strategies "
                     "(id, account_id, source_recommendation_id, version, status, positioning, target_audience, "
                     "content_pillars_json, experiment_plan_json, confidence_at_confirmation, confirmed_at, "
                     "confirmed_by, created_at, updated_at) "
                     "VALUES ('calendar-strategy', 'douyin-pet', 'calendar-rec', 1, 'ACTIVE', '双猫家庭', '猫咪观众', "
                     "?, '{}', 'LOW', ?, 'test', ?, ?)",
                     (json.dumps([{"id": "calendar-pillar", "name": "日常陪伴", "status": "ACTIVE"}], ensure_ascii=False),
                      now, now, now))
        conn.execute("INSERT INTO operator_content_pillars "
                     "(id, account_id, strategy_id, name, description, allocation_ratio, goal, experiment_question, "
                     "evidence_summary_json, status, created_at, updated_at) "
                     "VALUES ('calendar-pillar', 'douyin-pet', 'calendar-strategy', '日常陪伴', '猫咪日常', 100, "
                     "'验证日常', '反馈如何？', '[]', 'ACTIVE', ?, ?)", (now, now))
        conn.execute("INSERT INTO operator_topic_batches "
                     "(id, account_id, strategy_id, local_date, batch_number, generated_at, generation_mode, status) "
                     "VALUES ('calendar-batch', 'douyin-pet', 'calendar-strategy', '2026-09-21', 1, ?, 'AI', 'CURRENT')",
                     (now,))
        conn.execute("INSERT INTO operator_topics "
                     "(id, batch_id, account_id, strategy_id, pillar_id, title, angle, description, score, "
                     "score_breakdown_json, recommendation_reason, historical_evidence_json, experiment_question, "
                     "production_difficulty, material_requirements_json, status, created_at) "
                     "VALUES ('calendar-topic', 'calendar-batch', 'douyin-pet', 'calendar-strategy', 'calendar-pillar', "
                     "'猫咪午后日常', '观察自然休息', '记录真实日常', 80, '{}', '测试方向', '[]', '反馈如何？', "
                     "'EASY', '[]', 'SELECTED', ?)", (now,))
    return repo, OperatorContentCalendarService(repo)


def test_calendar_flow_publishes_manually_and_blocks_insufficient_review(tmp_path):
    repo, calendar = _setup(tmp_path)
    context = calendar.context("douyin-pet", "2026-09-01", "2026-09-30")
    assert context["selected_topics"][0]["id"] == "calendar-topic"
    assert context["calendar_items"] == []

    item = calendar.schedule("douyin-pet", "calendar-topic", None, "2026-09-22T19:00:00+08:00")
    assert item["status"] == "SELECTED" and item["strategy_version"] == 1
    moved = calendar.reschedule("douyin-pet", item["id"], "2026-09-23T20:00:00+08:00")
    assert moved["planned_publish_at"].startswith("2026-09-23T20:00:00+08:00")
    with pytest.raises(ValueError, match="只有标记为待发布"):
        calendar.mark_published("douyin-pet", item["id"], {
            "title": "尚未准备", "published_at": "2026-09-23T20:00:00+08:00", "content_source": "REAL",
        })
    ready = calendar.mark_ready("douyin-pet", item["id"])
    assert ready["status"] == "READY"

    published = calendar.mark_published("douyin-pet", item["id"], {
        "title": "真实发布的作品", "published_at": "2026-09-23T20:10:00+08:00",
        "published_url": "https://example.invalid/post/1", "content_source": "REAL",
    })
    assert published["status"] == "PUBLISHED" and published["published_post_id"]
    with repo._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM operator_published_posts").fetchone()[0] == 1
    with pytest.raises(ValueError, match="只有标记为待发布"):
        calendar.mark_published("douyin-pet", item["id"], {
            "title": "重复发布", "published_at": "2026-09-23T20:10:00+08:00", "content_source": "REAL",
        })

    feedback = WeeklyReviewService(repo)
    feedback.record_metrics("douyin-pet", published["published_post_id"], "7D", {
        "views": 120, "likes": 4, "comments": 1, "favorites": 0, "shares": 0,
    })
    with pytest.raises(ValueError, match="当前发布样本不足，暂无法形成有效周复盘"):
        feedback.generate("douyin-pet", "2026-09-21")
    reviewed = calendar.context("douyin-pet", "2026-09-01", "2026-09-30")["calendar_items"][0]
    assert reviewed["status"] == "PUBLISHED" and reviewed["review_id"] is None

    feedback.record_metrics("douyin-pet", published["published_post_id"], "7D", {
        "views": 150, "likes": 5, "comments": 1,
    })
    still_published = calendar.context("douyin-pet", "2026-09-01", "2026-09-30")["calendar_items"][0]
    assert still_published["status"] == "PUBLISHED" and still_published["review_id"] is None
    event_types = [event["event_type"] for event in still_published["events"]]
    assert event_types == ["SCHEDULED", "RESCHEDULED", "READY", "PUBLISHED"]


def test_calendar_cancellation_allows_replan_and_account_isolation(tmp_path):
    repo, calendar = _setup(tmp_path)
    item = calendar.schedule("douyin-pet", "calendar-topic", None, "2026-09-22T19:00:00+08:00")
    with pytest.raises(ValueError, match="已有一条有效日历计划"):
        calendar.schedule("douyin-pet", "calendar-topic", None, "2026-09-24T19:00:00+08:00")
    cancelled = calendar.cancel("douyin-pet", item["id"])
    assert cancelled["status"] == "CANCELLED"
    replacement = calendar.schedule("douyin-pet", "calendar-topic", None, "2026-09-24T19:00:00+08:00")
    assert replacement["status"] == "SELECTED" and replacement["id"] != item["id"]
    with pytest.raises(ValueError, match="不属于当前账号"):
        calendar.cancel("xhs-developer", item["id"])
    with pytest.raises(ValueError, match="时间必须包含时区"):
        calendar.reschedule("douyin-pet", replacement["id"], "2026-09-25T18:00:00")


def test_weekly_review_publication_entry_links_existing_calendar_plan(tmp_path):
    repo, calendar = _setup(tmp_path)
    item = calendar.schedule("douyin-pet", "calendar-topic", None, "2026-09-22T19:00:00+08:00")
    feedback = WeeklyReviewService(repo)
    post = feedback.register_published_post("douyin-pet", topic_id="calendar-topic", draft_id=None, values={
        "title": "从周复盘页登记的真实发布", "published_at": "2026-09-22T19:20:00+08:00",
        "published_url": None, "content_source": "REAL",
    })
    linked = calendar.context("douyin-pet", "2026-09-01", "2026-09-30")["calendar_items"][0]
    assert linked["id"] == item["id"] and linked["status"] == "PUBLISHED"
    assert linked["published_post_id"] == post["id"]
    with pytest.raises(ValueError, match="不能重复登记"):
        feedback.register_published_post("douyin-pet", topic_id="calendar-topic", draft_id=None, values={
            "title": "重复记录", "published_at": "2026-09-22T19:20:00+08:00", "content_source": "REAL",
        })


def test_calendar_api_serves_month_and_enforces_strategy_scope(tmp_path):
    repo, service = _setup(tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        context = client.get("/api/operator/accounts/douyin-pet/calendar", params={"start": "2026-09-01", "end": "2026-09-30"})
        assert context.status_code == 200 and context.json()["selected_topics"][0]["id"] == "calendar-topic"
        payload = {"topic_id": "calendar-topic", "planned_publish_at": "2026-09-22T11:00:00+08:00"}
        created = client.post("/api/operator/accounts/douyin-pet/calendar", json=payload)
        assert created.status_code == 201 and created.json()["status"] == "SELECTED"
        denied = client.post("/api/operator/accounts/xhs-developer/calendar", json=payload)
        assert denied.status_code == 409
        invalid_range = client.get("/api/operator/accounts/douyin-pet/calendar", params={"start": "2026-09-30", "end": "2026-09-01"})
        assert invalid_range.status_code == 409
    finally:
        app.dependency_overrides.pop(get_service, None)
