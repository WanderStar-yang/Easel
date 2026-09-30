from __future__ import annotations

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from easel.social_operator.historical import (
    DuplicateHistoricalPostError,
    HistoricalPostService,
    InvalidHistoricalPostError,
)
from easel.social_operator.historical_imports import HistoricalImportManager
from easel.social_operator.repository import OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService
from web.routers.historical_posts import HistoricalServices, get_historical_services


@pytest.fixture
def services(tmp_path):
    repository = OperatorAccountRepository(tmp_path / "operator.sqlite3")
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    return HistoricalServices(accounts, posts, HistoricalImportManager(posts, repository))


def test_manual_crud_and_account_isolation(services):
    post = services.posts.create_post("douyin-pet", {
        "title": "双猫抢位置", "publish_time": "2025-01-02", "content_type": "双猫互动",
        "content_source": "REAL", "views": 1200, "likes": 80, "comments": 12,
        "tags": ["双猫", "日常"], "subjects": ["缅因", "布偶"],
    })
    assert post.platform.value == "douyin"
    assert post.account_id == "douyin-pet"
    assert len(services.posts.list_posts("douyin-pet")) == 1
    assert services.posts.list_posts("xhs-developer") == []
    updated = services.posts.update_post("douyin-pet", post.id, {"title": "抢窝大战", "likes": 90})
    assert updated.title == "抢窝大战"
    assert updated.likes == 90
    with pytest.raises(LookupError):
        services.posts.get_post("xhs-developer", post.id)
    with pytest.raises(LookupError):
        services.posts.delete_post("xhs-developer", post.id)
    services.posts.delete_post("douyin-pet", post.id)
    assert services.posts.list_posts("douyin-pet") == []


def test_platform_post_id_and_composite_duplicate_detection(services):
    first = services.posts.create_post("douyin-pet", {
        "title": "一条作品", "publish_time": "2025-01-02", "platform_post_id": "aweme-1",
    })
    with pytest.raises(DuplicateHistoricalPostError):
        services.posts.create_post("douyin-pet", {
            "title": "改过标题", "publish_time": "2025-02-02", "platform_post_id": "aweme-1",
        })
    with pytest.raises(DuplicateHistoricalPostError):
        services.posts.create_post("douyin-pet", {
            "title": "一条作品", "publish_time": "2025-01-02",
        })
    xhs_post = services.posts.create_post("xhs-developer", {
        "title": "一条作品", "publish_time": "2025-01-02",
    })
    assert xhs_post.id != first.id


def test_validation_allows_missing_metrics_but_rejects_bad_values(services):
    post = services.posts.create_post("xhs-developer", {"title": "只知道标题"})
    assert post.views is None and post.likes is None
    with pytest.raises(InvalidHistoricalPostError, match="数字"):
        services.posts.create_post("douyin-pet", {"title": "非法播放", "views": "abc"})
    with pytest.raises(InvalidHistoricalPostError, match="日期格式"):
        services.posts.create_post("douyin-pet", {"title": "非法日期", "publish_time": "下周一"})
    with pytest.raises(InvalidHistoricalPostError, match="不能小于 0"):
        services.posts.create_post("douyin-pet", {"title": "负播放", "views": -1})


def test_completeness_uses_diagnostic_data_and_platform_metrics(services):
    empty = services.posts.completeness("douyin-pet")
    assert empty["score"] == 0 and empty["sample_size"] == 0
    services.posts.create_post("douyin-pet", {
        "title": "数据完整", "publish_time": "2025-01-02", "content_type": "双猫互动",
        "views": 100, "likes": 10, "comments": 2,
    })
    result = services.posts.completeness("douyin-pet")
    assert result["score"] == 100
    assert result["sample_size"] == 1
    assert result["coverage"]["interactions"] == 1

    services.posts.create_post("xhs-developer", {
        "title": "小红书数据", "publish_time": "2025-01-02", "content_type": "项目复盘",
        "exposure": 300, "likes": 3, "favorites": 5, "profile_visits": 20, "inquiries": 1,
    })
    xhs_post = services.posts.list_posts("xhs-developer")[0]
    assert xhs_post.views == 300
    assert xhs_post.as_dict()["exposure"] == 300
    assert services.posts.completeness("xhs-developer")["score"] == 100


def test_csv_preview_errors_missing_fields_duplicates_and_confirmation(services):
    csv_data = (
        "发布时间,标题,内容类型,内容来源,播放量,点赞,评论,作品ID\n"
        "2025-01-02,双猫抢位,双猫互动,REAL,1200,80,12,aweme-1\n"
        "2025-01-02,双猫抢位,双猫互动,REAL,1200,80,12,aweme-1\n"
        "2025-01-03,错误指标,日常,REAL,abc,1,0,aweme-2\n"
        "bad-date,错误日期,日常,REAL,100,1,0,aweme-3\n"
    ).encode("utf-8")
    preview_id, preview = services.imports.preview("douyin-pet", "history.csv", csv_data)
    assert preview["total_rows"] == 4
    assert preview["importable_count"] == 1
    assert preview["error_count"] == 2
    assert preview["duplicate_count"] == 1
    assert preview["rows"][2]["errors"]["views"] == "必须是数字"
    assert preview["rows"][3]["errors"]["publish_time"]
    assert services.posts.list_posts("douyin-pet") == []  # preview does not write
    result = services.imports.confirm("douyin-pet", preview_id)
    assert result["imported_count"] == 1
    assert result["skipped_duplicate_count"] == 1
    assert result["error_count"] == 2
    completeness = services.posts.completeness("douyin-pet")
    assert completeness["sample_size"] == 1
    assert completeness["score"] == 100


def test_xlsx_import_and_exposure_alias(services):
    buffer = io.BytesIO()
    pd.DataFrame([{
        "发布日期": "2025-01-02", "标题": "项目复盘", "内容类型": "项目过程",
        "曝光": 300, "点赞": 6, "收藏": 9, "主页访问量": 20, "咨询": 1,
    }]).to_excel(buffer, index=False, engine="openpyxl")
    preview_id, preview = services.imports.preview("xhs-developer", "history.xlsx", buffer.getvalue())
    assert preview["total_rows"] == 1
    assert preview["importable_count"] == 1
    assert not preview["error_count"]
    result = services.imports.confirm("xhs-developer", preview_id)
    assert result["imported_count"] == 1
    post = services.posts.list_posts("xhs-developer")[0]
    assert post.views == 300
    assert post.profile_visits == 20 and post.inquiries == 1


def test_douyin_creator_export_headers_import_and_report_unsupported_columns(services):
    buffer = io.BytesIO()
    pd.DataFrame([{
        "作品名称": "双猫日常", "发布时间": "2026-09-28 19:17:51", "体裁": "图文", "审核状态": "公开",
        "播放量": 908, "完播率": 0.144404, "5s完播率": 0.144404, "封面点击率": 0,
        "2s跳出率": 0.583333, "平均播放时长": 3.150901, "点赞量": 14, "分享量": 1,
        "评论量": 6, "收藏量": 0, "主页访问量": 2, "粉丝增量": 1,
    }]).to_excel(buffer, index=False, engine="openpyxl")

    preview_id, preview = services.imports.preview("douyin-pet", "作品列表导出.xlsx", buffer.getvalue())

    assert preview["total_rows"] == 1
    assert preview["importable_count"] == 1
    assert preview["error_count"] == 0
    assert preview["rows"][0]["record"]["title"] == "双猫日常"
    assert preview["rows"][0]["record"]["content_type"] == "图文"
    assert preview["rows"][0]["record"]["likes"] == 14
    assert preview["rows"][0]["record"]["comments"] == 6
    assert preview["rows"][0]["record"]["favorites"] == 0
    assert preview["rows"][0]["record"]["shares"] == 1
    assert preview["rows"][0]["record"]["followers_gain"] == 1
    assert set(preview["ignored_columns"]) == {
        "审核状态", "完播率", "5s完播率", "封面点击率", "2s跳出率", "平均播放时长",
    }
    assert services.posts.list_posts("douyin-pet") == []
    assert services.imports.confirm("douyin-pet", preview_id)["imported_count"] == 1
    saved = services.posts.list_posts("douyin-pet")[0]
    assert saved.views == 908 and saved.profile_visits == 2 and saved.followers_gain == 1


def test_empty_file_and_missing_columns_are_previewable(services):
    preview_id, empty = services.imports.preview("douyin-pet", "empty.csv", b"")
    assert empty["total_rows"] == 0 and empty["error_count"] == 0
    assert services.imports.confirm("douyin-pet", preview_id)["imported_count"] == 0
    _, missing = services.imports.preview("douyin-pet", "partial.csv", "title\n只有标题\n".encode("utf-8"))
    assert missing["importable_count"] == 1
    assert {field["field"] for field in missing["missing_fields"]} >= {
        "publish_time", "content_type", "views", "likes", "comments", "favorites",
    }


def test_preview_is_scoped_to_account_and_expires_or_consumes(services):
    preview_id, _ = services.imports.preview("douyin-pet", "one.csv", "title\n猫\n".encode("utf-8"))
    with pytest.raises(LookupError):
        services.imports.confirm("xhs-developer", preview_id)
    services.imports.confirm("douyin-pet", preview_id)
    with pytest.raises(LookupError):
        services.imports.confirm("douyin-pet", preview_id)


def test_database_restart_keeps_posts_and_account_ownership(tmp_path):
    db = tmp_path / "operator.sqlite3"
    repository = OperatorAccountRepository(db)
    OperatorAccountService(repository)
    HistoricalPostService(repository).create_post("douyin-pet", {
        "title": "重启后仍在", "publish_time": "2025-01-02", "views": 77,
    })
    restarted_repository = OperatorAccountRepository(db)
    OperatorAccountService(restarted_repository)
    posts = HistoricalPostService(restarted_repository)
    assert posts.list_posts("douyin-pet")[0].views == 77
    assert posts.list_posts("xhs-developer") == []


def test_api_crud_import_and_original_account_api_remain_separate(services):
    from web.app import app

    app.dependency_overrides[get_historical_services] = lambda: services
    try:
        local = "http://127.0.0.1:7860"
        with TestClient(app, base_url=local, client=("127.0.0.1", 51234),
                        headers={"Origin": local}) as client:
            created = client.post("/api/operator/accounts/douyin-pet/posts", json={
                "title": "API 手工录入", "publish_time": "2025-01-02", "views": 100,
            })
            assert created.status_code == 201, created.text
            post_id = created.json()["id"]
            assert created.json()["account_id"] == "douyin-pet"
            assert client.get("/api/operator/accounts/xhs-developer/posts").json()["total"] == 0
            assert client.get(f"/api/operator/accounts/xhs-developer/posts/{post_id}").status_code == 404
            assert client.patch(f"/api/operator/accounts/douyin-pet/posts/{post_id}",
                                json={"likes": "bad"}).status_code == 422
            assert client.patch(f"/api/operator/accounts/douyin-pet/posts/{post_id}",
                                json={"note": "updated"}).status_code == 200
            assert client.get("/api/operator/accounts/douyin-pet/posts/completeness").json()["sample_size"] == 1
            uploaded = client.post(
                "/api/operator/accounts/xhs-developer/posts/imports/preview",
                files={"file": ("empty.csv", b"", "text/csv")},
            )
            assert uploaded.status_code == 200, uploaded.text
            preview_id = uploaded.json()["preview_id"]
            assert uploaded.json()["total_rows"] == 0
            confirmed = client.post(
                "/api/operator/accounts/xhs-developer/posts/imports/confirm",
                json={"preview_id": preview_id},
            )
            assert confirmed.status_code == 200
            assert client.delete(f"/api/operator/accounts/douyin-pet/posts/{post_id}").json()["deleted"]
            assert client.get("/api/accounts").status_code == 200
    finally:
        app.dependency_overrides.pop(get_historical_services, None)
