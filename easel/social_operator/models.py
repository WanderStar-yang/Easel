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


class ContentSource(str, Enum):
    REAL = "REAL"
    AI = "AI"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class HistoricalDataSource(str, Enum):
    DOUYIN_OPEN_API = "DOUYIN_OPEN_API"
    DOUYIN_CREATOR_CENTER = "DOUYIN_CREATOR_CENTER"
    FILE_IMPORT = "FILE_IMPORT"
    MANUAL = "MANUAL"


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


@dataclass(frozen=True)
class HistoricalPost:
    id: str
    account_id: str
    platform: Platform
    publish_time: str | None
    title: str
    content_type: str | None
    content_source: ContentSource
    tags: list[str]
    note: str | None
    duration: float | None
    subjects: list[str]
    hook_type: str | None
    views: int | None
    likes: int | None
    comments: int | None
    favorites: int | None
    shares: int | None
    followers_gain: int | None
    profile_visits: int | None
    inquiries: int | None
    platform_post_id: str | None
    data_source: str
    source_updated_at: str | None
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "platform": self.platform.value,
            "publish_time": self.publish_time,
            "title": self.title,
            "content_type": self.content_type,
            "content_source": self.content_source.value,
            "tags": self.tags,
            "note": self.note,
            "duration": self.duration,
            "subjects": self.subjects,
            "hook_type": self.hook_type,
            "views": self.views,
            "exposure": self.views if self.platform == Platform.XIAOHONGSHU else None,
            "likes": self.likes,
            "comments": self.comments,
            "favorites": self.favorites,
            "shares": self.shares,
            "followers_gain": self.followers_gain,
            "profile_visits": self.profile_visits,
            "inquiries": self.inquiries,
            "platform_post_id": self.platform_post_id,
            "data_source": self.data_source,
            "source_updated_at": self.source_updated_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class AccountDiagnosis:
    id: str
    account_id: str
    generated_at: str
    algorithm_version: str
    report: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "generated_at": self.generated_at,
            "algorithm_version": self.algorithm_version,
            **self.report,
        }
