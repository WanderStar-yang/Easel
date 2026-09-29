"""Business rules and state transitions for operator accounts."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from easel.persona import list_personas, profile_exists

from .models import AccountStatus, OperatorAccount, OperatorProfile, OperatorStrategy, Platform
from .repository import (
    AccountNotFoundError,
    DuplicatePlatformError,
    OperatorAccountRepository,
)

_ALLOWED_TRANSITIONS = {
    AccountStatus.NEW: {AccountStatus.IMPORTING},
    AccountStatus.IMPORTING: {AccountStatus.DIAGNOSING},
    AccountStatus.DIAGNOSING: {AccountStatus.STRATEGY_PENDING_CONFIRMATION},
    AccountStatus.STRATEGY_PENDING_CONFIRMATION: {AccountStatus.ACTIVE},
    AccountStatus.ACTIVE: {AccountStatus.REVIEWING},
    AccountStatus.REVIEWING: {AccountStatus.ACTIVE},
}


class InvalidTransitionError(ValueError):
    pass


class AccountNotActiveError(ValueError):
    pass


class InvalidProfileReferenceError(ValueError):
    pass


class OperatorAccountService:
    def __init__(self, repository: OperatorAccountRepository | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.repository.initialize()
        self.repository.seed_defaults(self._now())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _to_model(row: dict) -> OperatorAccount:
        profile, strategy = row["profile"], row["strategy"]
        return OperatorAccount(
            id=row["id"], name=row["name"], platform=Platform(row["platform"]),
            status=AccountStatus(row["status"]),
            profile=OperatorProfile(profile["id"], profile["account_id"], profile["summary"],
                                    profile["easel_profile_name"]),
            strategy=OperatorStrategy(strategy["id"], strategy["account_id"], strategy["summary"],
                                      strategy["state"], strategy["confirmed_at"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
            diagnosis_completed_at=row["diagnosis_completed_at"],
        )

    def list_accounts(self) -> list[OperatorAccount]:
        return [self._to_model(row) for row in self.repository.list_accounts()]

    def get_account(self, account_id: str) -> OperatorAccount:
        return self._to_model(self.repository.get_account(account_id))

    def require_active_account(self, account_id: str) -> OperatorAccount:
        """Server-side gate for future formal daily-operation entry points."""
        account = self.get_account(account_id)
        if account.status != AccountStatus.ACTIVE:
            raise AccountNotActiveError(f"Account {account_id} is not active")
        return account

    def create_account(self, *, name: str, platform: Platform, profile_summary: str = "",
                       strategy_summary: str = "") -> OperatorAccount:
        account_id = f"{platform.value}-{uuid4().hex[:12]}"
        row = self.repository.create_account(
            account_id=account_id, name=name, platform=platform.value,
            profile_summary=profile_summary, strategy_summary=strategy_summary, now=self._now(),
        )
        return self._to_model(row)

    def update_account(self, account_id: str, values: dict) -> OperatorAccount:
        current = self.get_account(account_id)
        update = dict(values)
        profile_name = update.get("easelProfileName", update.get("easel_profile_name"))
        if profile_name is not None and (profile_name not in list_personas() or not profile_exists(profile_name)):
            raise InvalidProfileReferenceError(f"Easel profile does not exist: {profile_name}")
        status = update.pop("status", None)
        if status is not None:
            target = AccountStatus(status)
            if target not in _ALLOWED_TRANSITIONS[current.status]:
                raise InvalidTransitionError(f"Cannot move {current.status.value} to {target.value}")
            row = self.repository.get_account(account_id)
            if target == AccountStatus.ACTIVE and (
                not row["diagnosis_completed_at"] or row["strategy"]["state"] != "confirmed"
                or not row["strategy"]["confirmed_at"]
            ):
                raise InvalidTransitionError("ACTIVE requires completed diagnosis and confirmed strategy")
            update["status"] = target.value
        normalized = {
            {"profileSummary": "profile_summary", "easelProfileName": "easel_profile_name",
             "strategySummary": "strategy_summary"}.get(key, key): value
            for key, value in update.items()
        }
        return self._to_model(self.repository.update_account(account_id, normalized, self._now()))
