"""Typed models for Social Operator business accounts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Platform(str, Enum):
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"


class AccountStatus(str, Enum):
    NEW = "NEW"
    IMPORTING = "IMPORTING"
    DIAGNOSING = "DIAGNOSING"
    STRATEGY_PENDING_CONFIRMATION = "STRATEGY_PENDING_CONFIRMATION"
    ACTIVE = "ACTIVE"
    REVIEWING = "REVIEWING"


@dataclass(frozen=True)
class OperatorProfile:
    id: str
    account_id: str
    summary: str
    easel_profile_name: str | None


@dataclass(frozen=True)
class OperatorStrategy:
    id: str
    account_id: str
    summary: str
    state: str
    confirmed_at: str | None


@dataclass(frozen=True)
class OperatorAccount:
    id: str
    name: str
    platform: Platform
    status: AccountStatus
    profile: OperatorProfile
    strategy: OperatorStrategy
    created_at: str
    updated_at: str
    diagnosis_completed_at: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "platform": self.platform.value,
            "status": self.status.value,
            "profile": {
                "id": self.profile.id,
                "summary": self.profile.summary,
                "easelProfileName": self.profile.easel_profile_name,
            },
            "strategy": {
                "id": self.strategy.id,
                "summary": self.strategy.summary,
                "state": self.strategy.state,
                "confirmedAt": self.strategy.confirmed_at,
            },
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
