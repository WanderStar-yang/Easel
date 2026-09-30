from __future__ import annotations

import json

from easel.social_operator.baselines import AccountBaselineService
from easel.ai_service import AIRuntimeState, ConfiguredAIService
from easel.social_operator.classification import (
    AIServiceHistoricalClassifier, HistoricalClassificationService,
)
from easel.social_operator.diagnosis import AccountDiagnosisService
from easel.social_operator.historical import HistoricalPostService
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from fastapi.testclient import TestClient
from web.app import app
from web.routers.historical_posts import HistoricalServices, get_historical_services
from easel.social_operator.historical_imports import HistoricalImportManager


def make_repo(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "classification.sqlite3")
    OperatorAccountService(repository)
    return repository


class FakeClassifier:
    def __init__(self, result_factory=None):
        self.calls = []
        self.result_factory = result_factory

    def classify_batch(self, rows):
        self.calls.append(rows)
        if self.result_factory:
            return self.result_factory(rows)
        results = []
        for index, row in enumerate(rows):
            results.append({
                "post_id": row["post_id"],
                "content_source": {"value": "REAL", "confidence": "HIGH", "reason": "标题明确说明实拍"},
                "subjects": {"value": "双猫", "confidence": "MEDIUM", "reason": "标题明确写两只猫"},
                "content_type": {"value": "双猫互动", "confidence": ["HIGH", "MEDIUM", "LOW"][index % 3], "reason": "标题线索"},
            })
        return results


def test_ai_suggestions_use_only_editorial_text_and_are_not_applied(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    post = posts.create_post("douyin-pet", {
        "title": "两只猫抢位置", "content_type_raw": "竖屏视频", "tags": ["双猫"], "note": "家里日常",
        "views": 693000, "likes": 1000,
    })
    model = FakeClassifier()
    service = HistoricalClassificationService(repo, model=model)
    result = service.suggest("douyin-pet")
    sent = model.calls[0][0]
    assert set(sent) == {"post_id", "title", "source_content_type", "tags", "description"}
    assert "views" not in sent and "likes" not in sent
    assert result["suggested_post_count"] == 1
    row = service.classification_rows("douyin-pet")[0]
    assert row["id"] == post.id
    assert row["content_source"] == "UNKNOWN"  # suggestion is not silently applied
    assert row["suggestion_status"] == "SUGGESTED"
    assert row["suggestions"]["subjects"]["value"] == "双猫"


def test_unknown_fallback_and_confidence_values_are_bounded():
    invalid = AIServiceHistoricalClassifier._normalize_item({
        "content_source": {"value": "probably real", "confidence": "CERTAIN"},
        "subjects": {"value": "像缅因", "confidence": "HIGH"},
        "content_type": {"value": "爆款", "confidence": "HIGH"},
    }, "post-1")
    assert invalid["content_source"] == {"value": "UNKNOWN", "confidence": "LOW", "reason": ""}
    assert invalid["subjects"]["value"] == "UNKNOWN"
    assert invalid["content_type"]["value"] == "UNKNOWN"
    assert {"HIGH", "MEDIUM", "LOW"} <= {"HIGH", "MEDIUM", "LOW"}


def test_high_medium_low_confidence_are_preserved_per_field(tmp_path):
    repo = make_repo(tmp_path)
    HistoricalPostService(repo).create_post("douyin-pet", {"title": "双猫"})
    service = HistoricalClassificationService(repo, model=FakeClassifier())
    service.suggest("douyin-pet")
    row = service.classification_rows("douyin-pet")[0]
    assert row["suggestions"]["content_source"]["confidence"] == "HIGH"
    assert row["suggestions"]["subjects"]["confidence"] == "MEDIUM"
    assert row["suggestions"]["content_type"]["confidence"] == "HIGH"

    class LowConfidenceClassifier:
        def classify_batch(self, rows):
            return [{"post_id": row["post_id"], **{
                field: {"value": "UNKNOWN", "confidence": "LOW"} for field in ("content_source", "subjects", "content_type")
            }} for row in rows]

    # Confidence normalization accepts each documented level; malformed confidence falls back to LOW.
    assert AIServiceHistoricalClassifier._normalize_item({"subjects": {"value": "缅因", "confidence": "LOW"}}, "x")["subjects"]["confidence"] == "LOW"
    assert AIServiceHistoricalClassifier._normalize_item({"subjects": {"value": "缅因", "confidence": "MEDIUM"}}, "x")["subjects"]["confidence"] == "MEDIUM"


def test_manual_confirmation_wins_and_ai_cannot_overwrite_it(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    post = posts.create_post("douyin-pet", {"title": "猫咪日常"})
    posts.classify_posts("douyin-pet", [post.id], {"content_source": "AI", "subjects": ["布偶"]})
    model = FakeClassifier()
    service = HistoricalClassificationService(repo, model=model)
    service.suggest("douyin-pet")
    row = service.classification_rows("douyin-pet")[0]
    assert "content_source" not in row["suggestions"]
    assert "subjects" not in row["suggestions"]
    assert row["metadata"]["content_source"]["source"] == "MANUAL_CONFIRMED"
    accepted = service.accept("douyin-pet", [post.id], ["content_source", "subjects", "content_type"])
    assert accepted == {"updated_count": 1, "confirmed_field_count": 1}
    current = posts.get_post("douyin-pet", post.id)
    assert current.content_source.value == "AI"
    assert current.subjects == ["布偶"]
    assert current.content_type == "双猫互动"


def test_batch_classification_records_manual_provenance_and_progress(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    first = posts.create_post("douyin-pet", {"title": "一"})
    second = posts.create_post("douyin-pet", {"title": "二"})
    service = HistoricalClassificationService(repo, model=FakeClassifier())
    posts.classify_posts("douyin-pet", [first.id, second.id], {
        "content_source": "REAL", "subjects": ["缅因"], "content_type": "单猫日常",
    })
    progress = service.progress("douyin-pet")
    assert progress["content_source"] == {"classified_count": 2, "sample_size": 2, "coverage": 1.0}
    assert progress["subjects"]["coverage"] == 1.0
    overlay = repo.get_classification_overlay("douyin-pet", [first.id])
    assert overlay[first.id]["metadata"]["content_type"]["source"] == "MANUAL_CONFIRMED"
    assert overlay[first.id]["metadata"]["content_type"]["confirmed_at"]


def test_unclassified_low_confidence_and_suggested_filters_have_data_contract(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    unknown = posts.create_post("douyin-pet", {"title": "无法判断"})
    classified = posts.create_post("douyin-pet", {"title": "明确分类", "content_type": "其他"})
    class FilterClassifier:
        def classify_batch(self, rows):
            return [{"post_id": row["post_id"],
                     "content_source": {"value": "UNKNOWN", "confidence": "LOW"},
                     "subjects": {"value": "UNKNOWN", "confidence": "LOW"},
                     "content_type": {"value": "其他", "confidence": "HIGH"}} for row in rows]
    service = HistoricalClassificationService(repo, model=FilterClassifier())
    service.suggest("douyin-pet")
    rows = service.classification_rows("douyin-pet")
    unclassified = [row for row in rows if row["content_source"] == "UNKNOWN" or not row["subjects"]]
    low = [row for row in rows if any(item["confidence"] == "LOW" for item in row["suggestions"].values())]
    suggested = [row for row in rows if row["suggestion_status"] == "SUGGESTED"]
    assert {row["id"] for row in unclassified} == {unknown.id, classified.id}
    assert len(low) == len(suggested) == 2


def test_accept_high_confidence_reports_post_and_field_counts(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    post = posts.create_post("douyin-pet", {"title": "猫"})
    class HighLowClassifier:
        def classify_batch(self, rows):
            return [{"post_id": row["post_id"],
                     "content_source": {"value": "REAL", "confidence": "HIGH"},
                     "subjects": {"value": "UNKNOWN", "confidence": "LOW"},
                     "content_type": {"value": "单猫日常", "confidence": "HIGH"}} for row in rows]
    service = HistoricalClassificationService(repo, model=HighLowClassifier())
    service.suggest("douyin-pet")
    result = service.accept("douyin-pet", [post.id], ["content_source", "subjects", "content_type"],
                            high_confidence_only=True)
    assert result == {"updated_count": 1, "confirmed_field_count": 2}
    saved = posts.get_post("douyin-pet", post.id)
    assert saved.content_source.value == "REAL"
    assert saved.content_type == "单猫日常"
    assert saved.subjects == []


def test_accepting_classifications_stales_baseline_and_regeneration_adds_segments(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    for index in range(5):
        posts.create_post("douyin-pet", {"title": f"双猫互动 {index}", "views": 100 + index * 100,
                                           "likes": 5, "comments": 0})
    diagnosis = AccountDiagnosisService(repo)
    diagnosis.diagnose("douyin-pet")
    baseline = AccountBaselineService(repo)
    v1 = baseline.generate("douyin-pet")
    class SegmentClassifier:
        def classify_batch(self, rows):
            return [{"post_id": row["post_id"],
                     "content_source": {"value": "REAL", "confidence": "HIGH"},
                     "subjects": {"value": "双猫", "confidence": "HIGH"},
                     "content_type": {"value": "双猫互动", "confidence": "HIGH"}} for row in rows]
    classification = HistoricalClassificationService(repo, model=SegmentClassifier())
    classification.suggest("douyin-pet")
    rows = classification.classification_rows("douyin-pet")
    result = classification.accept("douyin-pet", [row["id"] for row in rows],
                                    ["content_source", "subjects", "content_type"])
    assert result["confirmed_field_count"] == 15
    assert baseline.latest("douyin-pet").status == "STALE"
    diagnosis.diagnose("douyin-pet")
    v2 = baseline.generate("douyin-pet")
    assert v2.version == 2 and v2.sample_size == 5
    assert v2.metrics["views"]["median"] == v1.metrics["views"]["median"]
    assert [group["key"] for group in v2.segments["content_source"]["groups"]] == ["REAL"]
    assert v2.segments["content_source"]["groups"][0]["sample_size"] == 5
    assert v2.segments["subjects"]["groups"][0]["key"] == "双猫"
    assert v2.segments["content_type"]["groups"][0]["eligible_for_comparison"] is True


def test_cross_account_suggestion_rows_and_acceptance_are_rejected(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    xhs_post = posts.create_post("xhs-developer", {"title": "开发"})
    service = HistoricalClassificationService(repo, model=FakeClassifier())
    try:
        service.accept("douyin-pet", [xhs_post.id], ["subjects"])
    except LookupError:
        pass
    else:
        raise AssertionError("cross-account classifications must be rejected")
    assert service.classification_rows("douyin-pet") == []


def test_runtime_status_distinguishes_missing_configuration_and_unavailable_gateway(monkeypatch):
    runtime = ConfiguredAIService(env={})
    monkeypatch.setattr(runtime, "_gateway_configured", lambda: False)
    monkeypatch.setattr(runtime, "_gateway_probe", lambda: False)
    assert runtime.runtime_status().state == AIRuntimeState.NOT_CONFIGURED


def test_openai_compatible_runtime_is_used_without_openclaw(monkeypatch):
    runtime = ConfiguredAIService(env={
        "OPENAI_BASE_URL": "https://models.example/v1", "OPENAI_API_KEY": "secret",
        "OPENAI_MODEL": "qwen-model",
    })
    monkeypatch.setattr("easel.ai_service._safe_public_url", lambda _url: True)
    monkeypatch.setattr(runtime, "_gateway_probe", lambda: False)
    monkeypatch.setattr(runtime, "_gateway_configured", lambda: False)

    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    get_calls = []
    post_calls = []
    monkeypatch.setattr("easel.ai_service.httpx.get", lambda url, **kwargs: get_calls.append((url, kwargs)) or Response())
    monkeypatch.setattr("easel.ai_service.httpx.post", lambda url, **kwargs: post_calls.append((url, kwargs)) or Response())
    assert runtime.runtime_status().state == AIRuntimeState.AVAILABLE
    assert runtime.complete("system", "user") == "ok"
    assert get_calls[0][0] == "https://models.example/v1/models"
    assert post_calls[0][0] == "https://models.example/v1/chat/completions"
    assert post_calls[0][1]["json"]["model"] == "qwen-model"
    assert post_calls[0][1]["headers"]["authorization"] == "Bearer secret"


def test_one_malformed_model_item_does_not_discard_other_results(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    good = posts.create_post("douyin-pet", {"title": "双猫互动"})
    bad = posts.create_post("douyin-pet", {"title": "另一条"})

    class PartialAIService:
        def runtime_status(self):
            from easel.ai_service import AIRuntimeStatus
            return AIRuntimeStatus(AIRuntimeState.AVAILABLE, "当前模型")

        def complete(self, _system, _user):
            return json.dumps({"classifications": [
                {"post_id": good.id,
                 "content_source": {"value": "REAL", "confidence": "HIGH"},
                 "subjects": {"value": "双猫", "confidence": "HIGH"},
                 "content_type": {"value": "双猫互动", "confidence": "HIGH"}},
                {"post_id": bad.id, "content_source": "bad"},
            ]}, ensure_ascii=False)

    service = HistoricalClassificationService(repo, ai_service=PartialAIService())
    result = service.suggest("douyin-pet")
    rows = {row["id"]: row for row in service.classification_rows("douyin-pet")}
    assert result["suggested_post_count"] == 1
    assert result["failed_post_count"] == 1
    assert rows[good.id]["suggestions"]["subjects"]["value"] == "双猫"
    assert rows[bad.id]["suggestions"] == {}


def test_invalid_batch_json_is_split_until_only_bad_item_fails():
    from easel.social_operator.classification import AIServiceHistoricalClassifier

    class RecoveringAIService:
        def complete(self, _system, user_prompt):
            rows = json.loads(user_prompt)["posts"]
            if len(rows) > 1:
                return "{not valid batch JSON"
            if rows[0]["post_id"] == "bad":
                return "not json"
            return json.dumps({"classifications": [{
                "post_id": rows[0]["post_id"],
                "content_source": {"value": "REAL", "confidence": "HIGH"},
                "subjects": {"value": "布偶", "confidence": "HIGH"},
                "content_type": {"value": "单猫日常", "confidence": "HIGH"},
            }]}, ensure_ascii=False)

    rows = AIServiceHistoricalClassifier(RecoveringAIService()).classify_batch([
        {"post_id": "good", "title": "good"}, {"post_id": "bad", "title": "bad"},
    ])
    assert [row["status"] for row in rows] == ["OK", "FAILED"]
    assert rows[0]["subjects"]["value"] == "布偶"


def test_classification_batches_at_most_twenty_and_continue_after_batch_error(tmp_path):
    repo = make_repo(tmp_path)
    posts = HistoricalPostService(repo)
    for index in range(41):
        posts.create_post("douyin-pet", {"title": f"作品 {index}", "views": 999999})

    class BatchModel:
        def __init__(self):
            self.calls = []

        def classify_batch(self, rows):
            self.calls.append(rows)
            assert all(set(row) == {"post_id", "title", "source_content_type", "tags", "description"} for row in rows)
            if len(self.calls) == 2:
                raise RuntimeError("one batch failed")
            return [{"post_id": row["post_id"], "content_source": {"value": "UNKNOWN", "confidence": "LOW"},
                     "subjects": {"value": "UNKNOWN", "confidence": "LOW"},
                     "content_type": {"value": "UNKNOWN", "confidence": "LOW"}} for row in rows]

    model = BatchModel()
    result = HistoricalClassificationService(repo, model=model).suggest("douyin-pet")
    assert [len(batch) for batch in model.calls] == [20, 20, 1]
    assert result["failed_post_count"] == 20
    assert result["suggested_post_count"] == 21


def test_classification_api_progress_and_account_isolation(tmp_path):
    repo = make_repo(tmp_path)
    accounts = OperatorAccountService(repo)
    posts = HistoricalPostService(repo)
    post = posts.create_post("douyin-pet", {"title": "作品"})
    services = HistoricalServices(accounts, posts, HistoricalImportManager(posts, repo),
                                  classification=HistoricalClassificationService(repo, model=FakeClassifier()))
    app.dependency_overrides[get_historical_services] = lambda: services
    try:
        local = "http://127.0.0.1:7860"
        with TestClient(app, base_url=local, client=("127.0.0.1", 51291), headers={"Origin": local}) as client:
            rows = client.get("/api/operator/accounts/douyin-pet/posts/classification/rows")
            assert rows.status_code == 200
            assert len(rows.json()["items"]) == 1
            progress = client.get("/api/operator/accounts/douyin-pet/posts/classification/progress").json()
            assert progress["sample_size"] == 1 and progress["content_type"]["coverage"] == 0
            accepted = client.post("/api/operator/accounts/douyin-pet/posts/classification/suggestions/accept", json={
                "post_ids": [post.id], "fields": ["subjects"],
            })
            assert accepted.status_code == 200
            foreign = client.get("/api/operator/accounts/xhs-developer/posts/classification/rows")
            assert foreign.json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_historical_services, None)
