from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from easel.ai_service import AIRuntimeState, AIRuntimeStatus, AIServiceError
from easel.social_operator.baselines import AccountBaselineService
from easel.social_operator.content_calendar import OperatorContentCalendarService
from easel.social_operator.content_generation import ContentGenerationService
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from easel.social_operator.strategy_confirmation import StrategyConfirmationService
from easel.social_operator.topic_recommendations import TopicRecommendationService
from easel.social_operator.weekly_review import WeeklyReviewService
from web.routers.operator_content_generation import get_content_generation_service, router


class DraftAI:
    def __init__(self, platform: str, *, fabricated_claim: bool = False, invalid_first_response: bool = False):
        self.platform = platform
        self.fabricated_claim = fabricated_claim
        self.invalid_first_response = invalid_first_response
        self.calls = 0
        self.user_payload = None
        self.system_prompt = None

    def runtime_status(self):
        return AIRuntimeStatus(AIRuntimeState.AVAILABLE, "test model")

    def complete(self, system_prompt, user_prompt):
        self.calls += 1
        self.system_prompt = system_prompt
        self.user_payload = json.loads(user_prompt)
        if self.platform == "douyin":
            result = {
                "content_theme": "记录猫咪的自然选择",
                "recommendation_reason": "对应已选方向，作为实验内容草稿。",
                "content_goal": "记录真实反应，观察观众反馈。",
                "hook": "两只猫会选择哪里休息？",
                "opening_3_seconds": "先展示两个位置，再记录猫咪自然靠近的过程。",
                "video_structure": [{"time_range": "0-3秒", "visual": "两个位置", "narration": "看看它们怎么选", "subtitle": "它们会选哪里？"}],
                "shot_suggestions": ["固定机位拍摄"], "subtitles": ["记录真实反应"],
                "suggested_duration_seconds": 30,
                "title_candidates": ["猫咪会选哪个位置？", "两只猫的休息选择", "今天它们想待哪里？", "记录猫咪自然反应", "双猫日常观察"],
                "bgm_type": "轻柔背景音乐", "hashtags": ["猫咪日常"],
                "comment_interaction": "你家猫更喜欢哪个位置？",
                "posting_time_suggestion": "选择你方便稳定更新的时段测试。",
                "existing_materials_to_verify": ["核对是否已有双猫同框片段"],
                "experiment_tag": "自然互动测试",
            }
        else:
            result = {
                "title_candidates": ["独立开发中的一个小问题", "这个开发取舍怎么判断？", "做小功能时先考虑什么？", "一个方法讨论：如何验证想法", "开发过程中的真实选择"],
                "cover_text": "一个开发取舍",
                "opening_hook": "做一个小功能时，先写测试还是先写业务逻辑？",
                "content_structure": ["提出问题", "说明两种方法", "补入真实项目背景", "总结待验证观察"],
                "body_markdown": "## 一个开发中的取舍\n\n请在这里补入一项可核实的真实经历，再介绍当时的考虑。\n\n## 可以怎么判断\n\n比较需求清晰度、验证成本和代码结构。",
                "image_structure": ["封面问题", "过程说明", "结尾总结"],
                "screenshot_suggestions": ["核实后使用不含隐私的真实界面截图"],
                "project_materials": ["需要时补入真实项目界面"], "cta": "你会怎么安排这个顺序？",
                "comment_interaction": "欢迎分享你的判断方式。",
                "recommended_topics": ["独立开发", "开发流程"],
                "posting_time_suggestion": "选择你方便稳定更新的时段测试。",
                "experiment_tag": "开发流程讨论",
            }
            if self.fabricated_claim:
                result["body_markdown"] = "我从0到1跑通了这个项目。"
        if self.invalid_first_response and self.calls == 1 and self.platform == "douyin":
            result["title_candidates"] = result["title_candidates"][:3]
        return json.dumps(result, ensure_ascii=False)


class TopicAI:
    def __init__(self):
        self.payload = None

    def runtime_status(self):
        return AIRuntimeStatus(AIRuntimeState.AVAILABLE, "test model")

    def complete(self, system_prompt, user_prompt):
        payload = json.loads(user_prompt)
        self.payload = payload
        return json.dumps({"topics": [
            {"pillar_id": pillar["id"], "title": f"可测试的{pillar['name']}主题{index + 1}",
             "angle": f"围绕{pillar['name']}观察一个真实场景", "description": "记录真实过程，作为实验草稿。",
             "material_requirements": ["真实场景记录"]}
            for index, pillar in enumerate(payload["pillars"][:3])
        ]}, ensure_ascii=False)


class ReviewAI:
    def __init__(self):
        self.payload = None

    def runtime_status(self):
        return AIRuntimeStatus(AIRuntimeState.AVAILABLE, "fixture")

    def complete(self, system_prompt, user_prompt):
        self.payload = json.loads(user_prompt)
        return json.dumps({"summary": "播放表现高于账号历史中位数，继续观察该方向。",
                           "observations": ["本次差异仅为描述性观察。"],
                           "next_steps": ["继续记录后续真实作品的数据。"]}, ensure_ascii=False)


class StaticRecommendations:
    def __init__(self, item):
        self.item = item

    def latest(self, account_id):
        return self.item if self.item and self.item["account_id"] == account_id else None


def _selected_topic(tmp_path, account_id: str, sample_size: int):
    repository = OperatorAccountRepository(tmp_path / "content-generation.sqlite3")
    accounts = OperatorAccountService(repository)
    now = "2026-10-01T00:00:00+00:00"
    body = {
        "status": "RECOMMENDED", "activation_status": "NOT_ACTIVATED", "confidence": "LOW",
        "confidence_note": "数据仍需验证。",
        "positioning_hypothesis": {"summary": "双猫家庭实验方向", "evidence_level": "EXPERIMENTAL"},
        "audience_hypothesis": {"summary": "对真实开发过程感兴趣的观众"},
        "source": {"canonical_sample_size": sample_size, "baseline_version": 1},
        "evidence": [],
        "pillars": [
            {"id": "p1", "name": "日常记录", "description": "记录日常", "initial_test_allocation": 34,
             "evidence_level": "EXPERIMENTAL", "evidence_ids": [], "goal": "测试持续性",
             "experiment_question": "真实场景反馈如何？", "why": "作为初步实验。"},
            {"id": "p2", "name": "互动观察", "description": "记录互动", "initial_test_allocation": 33,
             "evidence_level": "EXPERIMENTAL", "evidence_ids": [], "goal": "测试互动",
             "experiment_question": "互动反馈如何？", "why": "作为初步实验。"},
            {"id": "p3", "name": "趣味复盘", "description": "复盘过程", "initial_test_allocation": 33,
             "evidence_level": "EXPERIMENTAL", "evidence_ids": [], "goal": "测试表达",
             "experiment_question": "受众反馈是否可重复？", "why": "作为初步实验。"},
        ],
        "experiment_horizon_weeks": 4,
    }
    if sample_size:
        with sqlite3.connect(repository.db_path) as conn:
            conn.execute("UPDATE operator_accounts SET status='DIAGNOSING', diagnosis_completed_at=? WHERE id=?",
                         (now, account_id))
            conn.execute("INSERT INTO account_diagnoses "
                         "(id, account_id, algorithm_version, report_json, generated_at, status) "
                         "VALUES ('diag-1', ?, 'test', '{}', ?, 'CURRENT')", (account_id, now))
            conn.execute("INSERT INTO account_baselines "
                         "(id, account_id, version, sample_size, generated_at, historical_data_version, status, report_json) "
                         "VALUES ('base-1', ?, 1, ?, ?, 'version', 'ACTIVE', '{}')", (account_id, sample_size, now))
    recommendation = repository.save_strategy_recommendation(
        f"rec-{account_id}", account_id, baseline_id="base-1" if sample_size else None,
        baseline_version=1 if sample_size else None, diagnosis_id="diag-1" if sample_size else None,
        generated_at=now, evidence_data_version="version", recommendation=body,
    )
    confirmation = StrategyConfirmationService(
        repository, recommendations=StaticRecommendations(recommendation),
    )
    confirmation.confirm(account_id, {
        "recommendation_id": recommendation["id"],
        "positioning": body["positioning_hypothesis"]["summary"],
        "pillars": [{"recommendation_pillar_id": item["id"], "name": item["name"],
                     "description": item["description"], "allocation_ratio": item["initial_test_allocation"]}
                    for item in body["pillars"]],
    })
    topic_service = TopicRecommendationService(repository, ai=TopicAI())
    batch = topic_service.generate(account_id)
    selected_id = next(topic["id"] for topic in batch["topics"] if topic["status"] == "RECOMMENDED")
    selected_batch = topic_service.select(account_id, selected_id)
    return repository, selected_id, selected_batch


@pytest.mark.parametrize(("account_id", "sample_size", "platform"), [
    ("douyin-pet", 82, "douyin"), ("xhs-developer", 0, "xiaohongshu"),
])
def test_generates_platform_specific_versioned_draft_and_restarts(tmp_path, account_id, sample_size, platform):
    repository, topic_id, selected_batch = _selected_topic(tmp_path, account_id, sample_size)
    ai = DraftAI(platform)
    service = ContentGenerationService(repository, ai=ai)

    result = service.generate(account_id, topic_id)
    draft = result["draft"]
    assert draft["version"] == 1
    assert draft["status"] == "CURRENT"
    assert draft["platform"] == platform
    assert draft["strategy_id"] == selected_batch["topics"][0]["strategy_id"]
    assert draft["topic_id"] == topic_id
    if platform == "douyin":
        assert "恰好5个标题候选" in ai.system_prompt
        assert "不得为了拍摄故意设置不合尺寸或不安全的道具" in ai.system_prompt
        assert "用户选题仅是待验证的主题" in ai.system_prompt
    assert "views" not in ai.user_payload and "likes" not in ai.user_payload
    assert "score" not in ai.user_payload["selected_topic"]
    assert service.get(account_id, topic_id)["draft"]["id"] == draft["id"]

    second = service.generate(account_id, topic_id)["draft"]
    assert second["version"] == 2
    with sqlite3.connect(repository.db_path) as conn:
        rows = conn.execute("SELECT version, status FROM operator_content_drafts WHERE topic_id = ? ORDER BY version",
                            (topic_id,)).fetchall()
        events = conn.execute("SELECT event_type FROM operator_content_draft_events WHERE topic_id = ? ORDER BY occurred_at",
                              (topic_id,)).fetchall()
    assert rows == [(1, "SUPERSEDED"), (2, "CURRENT")]
    assert [event[0] for event in events] == ["GENERATED", "REGENERATED"]


def test_unselected_topic_is_rejected_before_model_call(tmp_path):
    repository, _topic_id, selected_batch = _selected_topic(tmp_path, "douyin-pet", 82)
    unselected = next(item for item in selected_batch["topics"] if item["status"] == "SKIPPED")
    ai = DraftAI("douyin")
    service = ContentGenerationService(repository, ai=ai)
    with pytest.raises(ValueError, match="先在今日运营中选择"):
        service.generate("douyin-pet", unselected["id"])
    assert ai.user_payload is None


def test_invalid_first_model_response_gets_one_bounded_repair_attempt(tmp_path):
    repository, topic_id, _ = _selected_topic(tmp_path, "douyin-pet", 82)
    ai = DraftAI("douyin", invalid_first_response=True)
    result = ContentGenerationService(repository, ai=ai).generate("douyin-pet", topic_id)
    assert ai.calls == 2
    assert result["draft"]["version"] == 1
    assert len(result["draft"]["content"]["title_candidates"]) == 5


def test_empty_reader_interaction_gets_neutral_default(tmp_path):
    repository, topic_id, _ = _selected_topic(tmp_path, "xhs-developer", 0)
    ai = DraftAI("xiaohongshu")
    original_complete = ai.complete

    def empty_interaction(system_prompt, user_prompt):
        result = json.loads(original_complete(system_prompt, user_prompt))
        result["comment_interaction"] = ""
        return json.dumps(result, ensure_ascii=False)

    ai.complete = empty_interaction
    result = ContentGenerationService(repository, ai=ai).generate("xhs-developer", topic_id)
    assert result["draft"]["content"]["comment_interaction"] == "你最想先尝试哪一点？欢迎在评论区分享。"


def test_model_read_timeout_is_reported_in_plain_language_and_saves_no_draft(tmp_path):
    repository, topic_id, _ = _selected_topic(tmp_path, "xhs-developer", 0)

    class TimedOutAI(DraftAI):
        def complete(self, system_prompt, user_prompt):
            raise AIServiceError(AIRuntimeState.UNAVAILABLE, "ReadTimeout")

    service = ContentGenerationService(repository, ai=TimedOutAI("xiaohongshu"))
    with pytest.raises(RuntimeError, match="模型暂时没有响应或请求超时"):
        service.generate("xhs-developer", topic_id)
    assert service.get("xhs-developer", topic_id)["draft"] is None


def test_unsafe_pet_staging_is_rejected_and_not_persisted(tmp_path):
    repository, topic_id, _ = _selected_topic(tmp_path, "douyin-pet", 82)
    ai = DraftAI("douyin")
    original_complete = ai.complete

    def unsafe_complete(system_prompt, user_prompt):
        result = json.loads(original_complete(system_prompt, user_prompt))
        result["video_structure"][0]["visual"] = "缅因猫挤进明显偏小的纸箱。"
        return json.dumps(result, ensure_ascii=False)

    ai.complete = unsafe_complete
    with pytest.raises(ValueError, match="不安全的宠物拍摄方式"):
        ContentGenerationService(repository, ai=ai).generate("douyin-pet", topic_id)
    assert ContentGenerationService(repository, ai=ai).get("douyin-pet", topic_id)["draft"] is None


def test_xhs_generated_fabricated_personal_history_is_rejected_and_not_persisted(tmp_path):
    repository, topic_id, _ = _selected_topic(tmp_path, "xhs-developer", 0)
    service = ContentGenerationService(repository, ai=DraftAI("xiaohongshu", fabricated_claim=True))
    with pytest.raises(ValueError, match="未经账号资料支持"):
        service.generate("xhs-developer", topic_id)
    assert service.get("xhs-developer", topic_id)["draft"] is None


def test_selected_topic_and_draft_are_isolated_between_accounts(tmp_path):
    repository, topic_id, _ = _selected_topic(tmp_path, "douyin-pet", 82)
    xhs_recommendation = repository.save_strategy_recommendation(
        "rec-xhs-isolation", "xhs-developer", baseline_id=None, baseline_version=None,
        diagnosis_id=None, generated_at="2026-10-01T00:00:00+00:00", evidence_data_version="empty",
        recommendation={
            "status": "RECOMMENDED", "activation_status": "NOT_ACTIVATED", "confidence": "LOW",
            "confidence_note": "起步假设。",
            "positioning_hypothesis": {"summary": "独立开发与真实项目记录", "evidence_level": "EXPERIMENTAL"},
            "audience_hypothesis": {"summary": "关注开发过程的人"}, "source": {"canonical_sample_size": 0},
            "evidence": [], "experiment_horizon_weeks": 4,
            "pillars": [
                {"id": "x1", "name": "项目实战", "description": "记录真实项目", "initial_test_allocation": 25,
                 "evidence_level": "EXPERIMENTAL", "evidence_ids": [], "goal": "测试", "experiment_question": "问题1", "why": "假设"},
                {"id": "x2", "name": "AI实践", "description": "记录AI实践", "initial_test_allocation": 25,
                 "evidence_level": "EXPERIMENTAL", "evidence_ids": [], "goal": "测试", "experiment_question": "问题2", "why": "假设"},
                {"id": "x3", "name": "开发复盘", "description": "记录复盘", "initial_test_allocation": 25,
                 "evidence_level": "EXPERIMENTAL", "evidence_ids": [], "goal": "测试", "experiment_question": "问题3", "why": "假设"},
                {"id": "x4", "name": "独立开发", "description": "记录独立开发", "initial_test_allocation": 25,
                 "evidence_level": "EXPERIMENTAL", "evidence_ids": [], "goal": "测试", "experiment_question": "问题4", "why": "假设"},
            ],
        },
    )
    StrategyConfirmationService(repository, recommendations=StaticRecommendations(xhs_recommendation)).confirm(
        "xhs-developer", {"recommendation_id": xhs_recommendation["id"], "positioning": "独立开发与真实项目记录",
                          "pillars": [{"recommendation_pillar_id": item["id"], "name": item["name"],
                                       "description": item["description"], "allocation_ratio": item["initial_test_allocation"]}
                                      for item in xhs_recommendation["recommendation"]["pillars"]]},
    )
    service = ContentGenerationService(repository, ai=DraftAI("douyin"))
    with pytest.raises(ValueError, match="请先在今日运营中选择"):
        service.generate("xhs-developer", topic_id)


def test_user_can_edit_draft_and_edit_is_audited_without_new_version(tmp_path):
    repository, topic_id, _ = _selected_topic(tmp_path, "xhs-developer", 0)
    service = ContentGenerationService(repository, ai=DraftAI("xiaohongshu"))
    draft = service.generate("xhs-developer", topic_id)["draft"]
    content = dict(draft["content"])
    content["body_markdown"] = "我在自己的真实项目中采用了这个步骤，稍后补入实际细节。"
    updated = service.update("xhs-developer", topic_id, content)["draft"]
    assert updated["id"] == draft["id"]
    assert updated["version"] == 1
    assert updated["content"]["body_markdown"] == content["body_markdown"]
    with sqlite3.connect(repository.db_path) as conn:
        events = conn.execute("SELECT event_type FROM operator_content_draft_events WHERE topic_id = ? ORDER BY occurred_at",
                              (topic_id,)).fetchall()
    assert [event[0] for event in events] == ["GENERATED", "EDITED"]


def test_content_draft_api_requires_selected_topic_and_persists_edit(tmp_path):
    repository, topic_id, batch = _selected_topic(tmp_path, "douyin-pet", 82)
    service = ContentGenerationService(repository, ai=DraftAI("douyin"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_content_generation_service] = lambda: service
    client = TestClient(app)
    unselected_id = next(topic["id"] for topic in batch["topics"] if topic["status"] == "SKIPPED")

    denied = client.post(f"/api/operator/accounts/douyin-pet/topics/{unselected_id}/content-draft/generate")
    assert denied.status_code == 422
    generated = client.post(f"/api/operator/accounts/douyin-pet/topics/{topic_id}/content-draft/generate")
    assert generated.status_code == 201
    draft = generated.json()["draft"]
    loaded = client.get(f"/api/operator/accounts/douyin-pet/topics/{topic_id}/content-draft")
    assert loaded.status_code == 200
    assert loaded.json()["draft"]["id"] == draft["id"]
    content = loaded.json()["draft"]["content"]
    content["hook"] = "用户审核后修改的 Hook"
    updated = client.put(f"/api/operator/accounts/douyin-pet/topics/{topic_id}/content-draft",
                         json={"content": content})
    assert updated.status_code == 200
    assert updated.json()["draft"]["content"]["hook"] == "用户审核后修改的 Hook"


def test_r1_core_closed_loop_from_active_strategy_through_confirmed_memory(tmp_path, monkeypatch):
    repository, first_topic_id, first_batch = _selected_topic(tmp_path, "douyin-pet", 82)
    target_pillar_id = next(topic["pillar_id"] for topic in first_batch["topics"] if topic["id"] == first_topic_id)
    topic_ai = TopicAI()
    topics = TopicRecommendationService(repository, ai=topic_ai)
    drafts = ContentGenerationService(repository, ai=DraftAI("douyin"))
    calendar = OperatorContentCalendarService(repository)
    review_ai = ReviewAI()
    feedback = WeeklyReviewService(repository, ai=review_ai)
    baseline = {"metrics": {
        "views": {"median": 100}, "engagement_rate": {"median": 0.01},
        "likes": {"median": 2}, "comments": {"median": 0}, "favorites": {"median": 0},
        "shares": {"median": 0}, "followers_gain": {"median": 0},
        "profile_visits": {"median": 0}, "inquiries": {"median": 0},
    }}
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute("UPDATE account_baselines SET report_json = ?, historical_data_version = ? WHERE id = 'base-1'",
                     (json.dumps(baseline), AccountBaselineService(repository).current_data_version("douyin-pet")))

    current_time = [datetime(2026, 9, 22, 12, tzinfo=timezone(timedelta(hours=8)))]
    monkeypatch.setattr(TopicRecommendationService, "_now", staticmethod(lambda: current_time[0]))
    topic_ids = [first_topic_id]
    for offset in range(3):
        day = 22 + offset
        current_time[0] = datetime(2026, 9, day, 12, tzinfo=timezone(timedelta(hours=8)))
        if offset:
            batch = topics.generate("douyin-pet")
            choice = next(topic for topic in batch["topics"] if topic["pillar_id"] == target_pillar_id)
            topics.select("douyin-pet", choice["id"])
            topic_ids.append(choice["id"])
        topic_id = topic_ids[offset]
        draft = drafts.generate("douyin-pet", topic_id)["draft"]
        plan = calendar.schedule("douyin-pet", topic_id, draft["id"], f"2026-09-{day:02d}T19:00:00+08:00")
        assert plan["status"] == "DRAFT"
        calendar.mark_ready("douyin-pet", plan["id"])
        published = calendar.mark_published("douyin-pet", plan["id"], {
            "title": f"测试数据库中的发布作品 {offset + 1}",
            "published_at": f"2026-09-{day:02d}T19:10:00+08:00",
            "content_source": "REAL", "platform_post_id": f"fixture-post-{offset + 1}",
        })
        assert published["status"] == "PUBLISHED"
        feedback.record_metrics("douyin-pet", published["published_post_id"], "7D", {
            "views": 150 + offset * 10, "likes": 8 + offset, "comments": 2, "favorites": 1, "shares": 1,
        })

    with sqlite3.connect(repository.db_path) as conn:
        conn.execute("UPDATE account_baselines SET status = 'ACTIVE', historical_data_version = ? WHERE id = 'base-1'",
                     (AccountBaselineService(repository).current_data_version("douyin-pet"),))
    review = feedback.generate("douyin-pet", "2026-09-21")
    assert review["report"]["published_count"] == 3
    assert review["report"]["checkpoint_summaries"]["7D"]["metrics"]["views"]["median"] == 160
    assert review["report"]["memory_candidates"], (review["report"]["baseline"], review["report"]["posts"])
    assert review["report"]["explanation"]["source"] == "AI"
    assert review_ai.payload["overall_metrics"]["views"]["median"] == 160
    candidate = next(memory for memory in review["memories"] if memory["status"] == "PROPOSED")
    feedback.decide_memory("douyin-pet", candidate["id"], confirm=True)
    current_time[0] = datetime(2026, 9, 25, 12, tzinfo=timezone(timedelta(hours=8)))
    next_batch = topics.generate("douyin-pet")
    assert topic_ai.payload["strategy_memory"]
    assert any("已确认经验" in item["recommendation_reason"] for item in next_batch["topics"])
