from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from easel.ai_service import AIRuntimeState, AIRuntimeStatus
from easel.social_operator.baselines import AccountBaselineService
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.topic_recommendations import TopicRecommendationService
from easel.social_operator.weekly_review import WeeklyReviewService
from web.routers.operator_feedback import get_service, router
from fastapi import FastAPI


def _repository(tmp_path):
    repo = OperatorAccountRepository(tmp_path / "feedback.sqlite3")
    repo.initialize()
    baseline_service = AccountBaselineService(repo)
    data_version = baseline_service.current_data_version("douyin-pet")
    with sqlite3.connect(repo.db_path) as conn:
        now = "2026-10-01T00:00:00+00:00"
        conn.execute("UPDATE operator_accounts SET status='ACTIVE', diagnosis_completed_at=? WHERE id='douyin-pet'", (now,))
        conn.execute("INSERT INTO strategy_recommendations "
                     "(id, account_id, version, generated_at, status, recommendation_json) "
                     "VALUES ('rec-feedback', 'douyin-pet', 1, ?, 'SUPERSEDED', '{}')", (now,))
        pillars = [
            {"id": "pillar-daily", "name": "日常陪伴", "description": "猫咪日常",
             "allocation_ratio": 36, "goal": "验证日常内容", "experiment_question": "反馈是否稳定？",
             "evidence_summary": [], "status": "ACTIVE"},
            {"id": "pillar-interaction", "name": "双猫互动", "description": "观察猫咪互动",
             "allocation_ratio": 31, "goal": "验证互动内容", "experiment_question": "互动是否稳定？",
             "evidence_summary": [], "status": "ACTIVE"},
            {"id": "pillar-fun", "name": "趣味记录", "description": "趣味记录",
             "allocation_ratio": 33, "goal": "验证趣味内容", "experiment_question": "反馈如何？",
             "evidence_summary": [], "status": "ACTIVE"},
        ]
        conn.execute("INSERT INTO operator_active_strategies "
                     "(id, account_id, source_recommendation_id, version, status, positioning, target_audience, "
                     "content_pillars_json, experiment_plan_json, confidence_at_confirmation, confirmed_at, "
                     "confirmed_by, created_at, updated_at) "
                     "VALUES ('strategy-feedback', 'douyin-pet', 'rec-feedback', 1, 'ACTIVE', '双猫家庭', '猫咪观众', ?, '{}', 'LOW', ?, 'test', ?, ?)",
                     (json.dumps(pillars, ensure_ascii=False), now, now, now))
        for pillar in pillars:
            conn.execute("INSERT INTO operator_content_pillars "
                         "(id, account_id, strategy_id, name, description, allocation_ratio, goal, experiment_question, "
                         "evidence_summary_json, status, created_at, updated_at) "
                         "VALUES (?, 'douyin-pet', 'strategy-feedback', ?, ?, ?, ?, ?, '[]', 'ACTIVE', ?, ?)",
                         (pillar["id"], pillar["name"], pillar["description"], pillar["allocation_ratio"],
                          pillar["goal"], pillar["experiment_question"], now, now))
        conn.execute("INSERT INTO operator_topic_batches "
                     "(id, account_id, strategy_id, local_date, batch_number, generated_at, generation_mode, status) "
                     "VALUES ('batch-feedback', 'douyin-pet', 'strategy-feedback', '2026-09-21', 1, ?, 'AI', 'CURRENT')", (now,))
        conn.execute("INSERT INTO operator_topics "
                     "(id, batch_id, account_id, strategy_id, pillar_id, title, angle, description, score, "
                     "score_breakdown_json, recommendation_reason, historical_evidence_json, experiment_question, "
                     "production_difficulty, material_requirements_json, status, created_at) "
                     "VALUES ('topic-feedback', 'batch-feedback', 'douyin-pet', 'strategy-feedback', 'pillar-daily', "
                     "'猫咪午后日常', '记录自然休息', '观察猫咪的日常状态', 80, '{}', '用于实验', '[]', '反馈如何？', 'EASY', '[]', 'SELECTED', ?)",
                     (now,))
        for index in (1, 2):
            conn.execute("INSERT INTO operator_topics "
                         "(id, batch_id, account_id, strategy_id, pillar_id, title, angle, description, score, "
                         "score_breakdown_json, recommendation_reason, historical_evidence_json, experiment_question, "
                         "production_difficulty, material_requirements_json, status, created_at) "
                         "VALUES (?, 'batch-feedback', 'douyin-pet', 'strategy-feedback', 'pillar-daily', ?, "
                         "'记录自然日常', '观察猫咪状态', 80, '{}', '用于实验', '[]', '反馈如何？', 'EASY', '[]', 'SELECTED', ?)",
                         (f"topic-feedback-{index}", f"猫咪日常选题 {index}", now))
    baseline_json = {"metrics": {
        "views": {"median": 100, "p25": 80, "p75": 120},
        "likes": {"median": 3, "p25": 1, "p75": 5},
        "comments": {"median": 1, "p25": 0, "p75": 2},
        "favorites": {"median": 1, "p25": 0, "p75": 2},
        "shares": {"median": 0, "p25": 0, "p75": 1},
        "followers_gain": {"median": 0, "p25": 0, "p75": 1},
        "profile_visits": {"median": 2, "p25": 1, "p75": 4},
        "inquiries": {"median": 0, "p25": 0, "p75": 0},
        "engagement_rate": {"median": 0.03, "p25": 0.02, "p75": 0.04},
    }}
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("INSERT INTO account_baselines "
                     "(id, account_id, version, sample_size, generated_at, historical_data_version, status, report_json) "
                     "VALUES ('baseline-feedback', 'douyin-pet', 1, 82, '2026-10-01T00:00:00+00:00', ?, 'ACTIVE', ?)",
                     (data_version, json.dumps(baseline_json)))
    return repo


class TopicAI:
    def __init__(self):
        self.payload = None

    def runtime_status(self):
        return AIRuntimeStatus(AIRuntimeState.AVAILABLE, "fixture")

    def complete(self, system_prompt, user_prompt):
        self.payload = json.loads(user_prompt)
        return json.dumps({"topics": [
            {"pillar_id": pillar["id"], "title": f"新主题 {index}", "angle": "观察一个自然时刻",
             "description": "记录猫咪自然互动并验证经验。", "material_requirements": ["手机拍摄"]}
            for index, pillar in enumerate(self.payload["pillars"])
        ]}, ensure_ascii=False)


class NoReviewAI:
    def runtime_status(self):
        return AIRuntimeStatus(AIRuntimeState.UNAVAILABLE)

    def complete(self, system_prompt, user_prompt):
        raise AssertionError("review explanation should use the local fallback")


def _three_posts(service: WeeklyReviewService):
    ids = []
    for index, views in enumerate((150, 160, 170)):
        topic_id = "topic-feedback" if index == 0 else f"topic-feedback-{index}"
        post = service.register_published_post("douyin-pet", topic_id=topic_id, draft_id=None, values={
            "title": f"猫咪日常 {index}", "published_at": f"2026-09-{22 + index:02d}T10:00:00+08:00",
            "published_url": None, "content_source": "REAL", "hook_type": "自然开场", "duration_seconds": 20,
        })
        ids.append(post["id"])
        service.record_metrics("douyin-pet", post["id"], "24H", {"views": views - 30, "likes": 3, "comments": None,
                              "favorites": 0, "shares": None, "followers_gain": None, "profile_visits": None, "inquiries": None})
        service.record_metrics("douyin-pet", post["id"], "7D", {"views": views, "likes": 5, "comments": 1,
                              "favorites": 0, "shares": 1, "followers_gain": 0, "profile_visits": 3, "inquiries": None})
    return ids


def test_review_uses_real_published_metrics_and_confirmed_memory_changes_next_topic(tmp_path):
    repo = _repository(tmp_path)
    service = WeeklyReviewService(repo, ai=NoReviewAI())
    post_ids = _three_posts(service)
    review = service.generate("douyin-pet", "2026-09-21")
    assert review["status"] == "CURRENT" and review["version"] == 1
    assert review["report"]["published_count"] == 3
    assert review["report"]["checkpoint_summaries"]["24H"]["metrics"]["views"]["median"] == 130
    week_7d = review["report"]["checkpoint_summaries"]["7D"]["metrics"]
    assert week_7d["views"]["median"] == 160
    assert week_7d["views"]["sample_count"] == 3
    assert week_7d["views"]["relative_to_baseline"] == 0.6
    assert week_7d["engagement_rate"]["sample_count"] == 3
    assert review["report"]["metric_coverage"] == {"24H": 3, "72H": 0, "7D": 3}
    assert review["memories"]
    candidate = review["memories"][0]
    assert candidate["status"] == "PROPOSED"
    assert service.feedback.list_active_strategy_memories("douyin-pet") == []

    service.decide_memory("douyin-pet", candidate["id"], confirm=True,
                          statement=candidate["statement"] + " 人工复核通过。")
    ai = TopicAI()
    batch = TopicRecommendationService(repo, ai=ai).generate("douyin-pet")
    assert ai.payload["strategy_memory"]
    daily_topic = next(item for item in batch["topics"] if item["pillar_id"] == "pillar-daily")
    assert "已确认经验" in daily_topic["recommendation_reason"]
    assert "不直接改写当前策略" in daily_topic["recommendation_reason"]

    service.record_metrics("douyin-pet", post_ids[0], "7D", {"views": 180, "likes": 5, "comments": 1,
                          "favorites": 0, "shares": 1, "followers_gain": 0, "profile_visits": 3, "inquiries": None})
    assert service.get_review("douyin-pet", review["id"])["status"] == "STALE"
    assert service.feedback.list_active_strategy_memories("douyin-pet") == []
    regenerated = service.generate("douyin-pet", "2026-09-21")
    assert regenerated["version"] == 2 and regenerated["status"] == "CURRENT"


def test_missing_values_zero_account_isolation_review_stale_and_restart(tmp_path):
    repo = _repository(tmp_path)
    service = WeeklyReviewService(repo, ai=NoReviewAI())
    post = service.register_published_post("douyin-pet", topic_id="topic-feedback", draft_id=None, values={
        "title": "作品", "published_at": "2026-09-22T10:00:00+08:00", "content_source": "REAL",
    })
    service.record_metrics("douyin-pet", post["id"], "7D", {"views": 0, "likes": 0, "comments": None,
                          "favorites": None, "shares": None, "followers_gain": None, "profile_visits": None, "inquiries": None})
    with pytest.raises(ValueError, match="当前发布样本不足"):
        service.generate("douyin-pet", "2026-09-21")
    for index in (1, 2):
        extra = service.register_published_post("douyin-pet", topic_id=f"topic-feedback-{index}", draft_id=None, values={
            "title": f"补充作品 {index}", "published_at": f"2026-09-{22 + index:02d}T10:00:00+08:00", "content_source": "REAL",
        })
        service.record_metrics("douyin-pet", extra["id"], "7D", {"views": 10, "likes": 0, "comments": None,
                              "favorites": None, "shares": None, "followers_gain": None, "profile_visits": None, "inquiries": None})
    review = service.generate("douyin-pet", "2026-09-21")
    rate = review["report"]["checkpoint_summaries"]["7D"]["metrics"]["engagement_rate"]
    assert rate["median"] == 0  # views == 0 is excluded; the two remaining true-zero samples remain valid
    assert rate["sample_count"] == 2
    assert review["report"]["checkpoint_summaries"]["7D"]["metrics"]["likes"]["median"] == 0
    with pytest.raises(ValueError, match="至少填写一个实际指标"):
        service.record_metrics("douyin-pet", post["id"], "72H", {field: None for field in (
            "views", "likes", "comments", "favorites", "shares", "followers_gain", "profile_visits", "inquiries")})
    with pytest.raises(ValueError, match="不属于当前账号"):
        service.record_metrics("xhs-developer", post["id"], "24H", {"views": 1})

    service.record_metrics("douyin-pet", post["id"], "7D", {"views": 10, "likes": 1, "comments": None,
                          "favorites": None, "shares": None, "followers_gain": None, "profile_visits": None, "inquiries": None})
    stale = service.get_review("douyin-pet", review["id"])
    assert stale["status"] == "STALE"
    restarted = WeeklyReviewService(OperatorAccountRepository(repo.db_path), ai=NoReviewAI())
    assert restarted.feedback.list_posts("douyin-pet")[0]["metrics"][0]["views"] == 10


def test_empty_week_invalid_week_and_review_api(tmp_path):
    repo = _repository(tmp_path)
    service = WeeklyReviewService(repo, ai=NoReviewAI())
    with pytest.raises(ValueError, match="暂无已登记的真实发布作品"):
        service.generate("douyin-pet", "2026-09-21")
    with pytest.raises(ValueError, match="必须是周一"):
        service.generate("douyin-pet", "2026-09-22")

    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        post = service.register_published_post("douyin-pet", topic_id="topic-feedback", draft_id=None, values={
            "title": "本周真实作品", "published_at": "2026-09-22T10:00:00+08:00", "content_source": "REAL",
        })
        service.record_metrics("douyin-pet", post["id"], "24H", {"views": 123})
        context = client.get("/api/operator/accounts/douyin-pet/feedback/context")
        assert context.status_code == 200 and context.json()["selected_topics"][0]["id"] == "topic-feedback"
        assert context.json()["published_posts"][0]["metrics"][0]["views"] == 123
        denied = client.post("/api/operator/accounts/xhs-developer/published-posts", json={
            "topic_id": "topic-feedback", "title": "cross account", "published_at": "2026-09-22T10:00:00+08:00",
        })
        assert denied.status_code == 409
        rejected = client.post("/api/operator/accounts/douyin-pet/weekly-reviews", json={"week_start": "2026-09-22"})
        assert rejected.status_code == 409
    finally:
        app.dependency_overrides.pop(get_service, None)
