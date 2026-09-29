from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from easel.social_operator import AccountStatus, OperatorAccountService, Platform
from easel.social_operator.repository import (
    DuplicatePlatformError,
    OperatorAccountRepository,
)
from easel.social_operator.service import (
    AccountNotActiveError,
    InvalidTransitionError,
)


@pytest.fixture
def service(tmp_path):
    return OperatorAccountService(OperatorAccountRepository(tmp_path / "operator.sqlite3"))


def test_seeds_two_distinct_business_accounts_with_separate_profile_and_strategy(service):
    accounts = service.list_accounts()
    assert [(a.id, a.platform, a.status) for a in accounts] == [
        ("douyin-pet", Platform.DOUYIN, AccountStatus.NEW),
        ("xhs-developer", Platform.XIAOHONGSHU, AccountStatus.NEW),
    ]
    assert accounts[0].profile.account_id == accounts[0].id
    assert accounts[1].profile.account_id == accounts[1].id
    assert accounts[0].strategy.account_id == accounts[0].id
    assert accounts[1].strategy.account_id == accounts[1].id
    assert accounts[0].profile.id != accounts[1].profile.id
    assert accounts[0].strategy.id != accounts[1].strategy.id


def test_account_scoped_updates_do_not_change_another_account(service):
    service.update_account("douyin-pet", {
        "name": "猫咪账号", "profileSummary": "只属于抖音", "strategySummary": "只属于抖音策略",
    })
    douyin = service.get_account("douyin-pet")
    xhs = service.get_account("xhs-developer")
    assert douyin.name == "猫咪账号"
    assert douyin.profile.summary == "只属于抖音"
    assert xhs.name == "小红书独立开发者账号"
    assert "只属于抖音" not in xhs.profile.summary
    assert "只属于抖音" not in xhs.strategy.summary


def test_platform_is_unique_and_invalid_platform_is_rejected(service):
    with pytest.raises(DuplicatePlatformError):
        service.create_account(name="另一个抖音账号", platform=Platform.DOUYIN)
    with pytest.raises(ValueError):
        Platform("instagram")


def test_state_machine_blocks_skips_and_active_until_prerequisites(service, tmp_path):
    with pytest.raises(InvalidTransitionError):
        service.update_account("douyin-pet", {"status": AccountStatus.ACTIVE})
    with pytest.raises(InvalidTransitionError):
        service.update_account("douyin-pet", {"status": AccountStatus.DIAGNOSING})
    service.update_account("douyin-pet", {"status": AccountStatus.IMPORTING})
    service.update_account("douyin-pet", {"status": AccountStatus.DIAGNOSING})
    service.update_account("douyin-pet", {"status": AccountStatus.STRATEGY_PENDING_CONFIRMATION})
    with pytest.raises(InvalidTransitionError, match="requires completed diagnosis"):
        service.update_account("douyin-pet", {"status": AccountStatus.ACTIVE})
    with sqlite3.connect(tmp_path / "operator.sqlite3") as conn:
        conn.execute("UPDATE operator_accounts SET diagnosis_completed_at = 'done' WHERE id = 'douyin-pet'")
    with pytest.raises(InvalidTransitionError, match="requires completed diagnosis"):
        service.update_account("douyin-pet", {"status": AccountStatus.ACTIVE})


def test_formal_operation_gate_rejects_non_active_account(service):
    with pytest.raises(AccountNotActiveError):
        service.require_active_account("douyin-pet")


def test_active_status_requires_both_prerequisites(service, tmp_path):
    service.update_account("douyin-pet", {"status": AccountStatus.IMPORTING})
    service.update_account("douyin-pet", {"status": AccountStatus.DIAGNOSING})
    service.update_account("douyin-pet", {"status": AccountStatus.STRATEGY_PENDING_CONFIRMATION})
    with sqlite3.connect(tmp_path / "operator.sqlite3") as conn:
        conn.execute("UPDATE operator_accounts SET diagnosis_completed_at = 'done' WHERE id = 'douyin-pet'")
        conn.execute(
            "UPDATE operator_strategies SET state = 'confirmed', confirmed_at = 'confirmed' "
            "WHERE account_id = 'douyin-pet'"
        )
    active = service.update_account("douyin-pet", {"status": AccountStatus.ACTIVE})
    assert active.status == AccountStatus.ACTIVE
    assert service.require_active_account("douyin-pet").id == "douyin-pet"


def test_database_survives_service_restart(tmp_path):
    db = tmp_path / "operator.sqlite3"
    first = OperatorAccountService(OperatorAccountRepository(db))
    first.update_account("douyin-pet", {"profileSummary": "persisted"})
    restarted = OperatorAccountService(OperatorAccountRepository(db))
    assert restarted.get_account("douyin-pet").profile.summary == "persisted"
    assert len(restarted.list_accounts()) == 2


def test_api_is_separate_and_scoped_to_operator_accounts(tmp_path):
    from web.app import app
    from web.routers.operator_accounts import get_service

    test_service = OperatorAccountService(OperatorAccountRepository(tmp_path / "api.sqlite3"))
    app.dependency_overrides[get_service] = lambda: test_service
    try:
        local = "http://127.0.0.1:7860"
        with TestClient(app, base_url=local, client=("127.0.0.1", 51234),
                        headers={"Origin": local}) as client:
            response = client.get("/api/operator/accounts")
            assert response.status_code == 200
            assert {row["platform"] for row in response.json()} == {"douyin", "xiaohongshu"}
            assert client.post("/api/operator/accounts", json={
                "name": "重复抖音账号", "platform": "douyin",
            }).status_code == 409
            assert client.post("/api/operator/accounts", json={
                "name": "无效平台账号", "platform": "instagram",
            }).status_code == 422
            assert client.get("/api/operator/accounts/missing").status_code == 404
            assert client.patch("/api/operator/accounts/douyin-pet", json={"profileSummary": "only cats"}).status_code == 200
            assert client.get("/api/operator/accounts/xhs-developer").json()["profile"]["summary"] != "only cats"
            assert client.patch("/api/operator/accounts/douyin-pet", json={"status": "ACTIVE"}).status_code == 409
            assert client.patch("/api/operator/accounts/douyin-pet", json={"profileSummary": None}).status_code == 422
            assert client.get("/api/accounts").status_code == 200
    finally:
        app.dependency_overrides.pop(get_service, None)
