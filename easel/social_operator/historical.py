"""Historical post CRUD, validation, and Phase 3 data completeness inputs."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from .models import ContentSource, HistoricalPost, Platform
from .data_sources import ManualInputAdapter
from .repository import AccountNotFoundError, OperatorAccountRepository

POST_FIELDS = (
    "publish_time", "publish_time_raw", "title", "content_type", "content_source", "tags", "note", "duration",
    "subjects", "hook_type", "views", "likes", "comments", "favorites", "shares",
    "followers_gain", "profile_visits", "inquiries", "platform_post_id",
)
LIST_FIELDS = {"tags", "subjects"}
METRIC_FIELDS = {
    "views", "likes", "comments", "favorites", "shares", "followers_gain",
    "profile_visits", "inquiries",
}
NON_NEGATIVE_FIELDS = METRIC_FIELDS - {"followers_gain"}


class InvalidHistoricalPostError(ValueError):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{field}: {message}" for field, message in errors.items()))


class DuplicateHistoricalPostError(ValueError):
    def __init__(self, duplicate_id: str):
        self.duplicate_id = duplicate_id
        super().__init__(f"Historical post duplicates existing post {duplicate_id}")


def _blank(value: object) -> bool:
    if value is None:
        return True
    try:
        # pandas NaN/NaT values can occur in imported spreadsheets.
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError, OverflowError):
        return isinstance(value, str) and not value.strip()


def _parse_datetime(value: object) -> str | None:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        raw = str(value).strip()
        parsed = None
        import re
        chinese = re.fullmatch(r"(20\d{2})年(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{2}))?", raw)
        if chinese:
            year, month, day, hour, minute = chinese.groups()
            parsed = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                              tzinfo=timezone(timedelta(hours=8)))
        try:
            if parsed is None:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y/%m/%d %H:%M", "%Y/%m/%d", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            raise ValueError("日期格式无效，请使用 YYYY-MM-DD 或 ISO 日期时间")
    return parsed.isoformat(timespec="seconds")


def _parse_number(value: object, field: str) -> int | float | None:
    if _blank(value):
        return None
    raw = str(value).strip().replace(",", "")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("必须是数字") from exc
    if not number.is_finite():
        raise ValueError("必须是有限数字")
    if field in METRIC_FIELDS and number != number.to_integral_value():
        raise ValueError("指标必须是整数")
    result: int | float = int(number) if field in METRIC_FIELDS else float(number)
    if field in NON_NEGATIVE_FIELDS and result < 0:
        raise ValueError("不能小于 0")
    if field == "duration" and result < 0:
        raise ValueError("时长不能小于 0")
    return result


def _parse_string_list(value: object, field: str) -> list[str]:
    if _blank(value):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value).strip()
    if raw.startswith("["):
        import json

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
    delimiter = ";" if ";" in raw else ("；" if "；" in raw else ("，" if "，" in raw else ","))
    return [item.strip() for item in raw.split(delimiter) if item.strip()]


def normalize_post(values: dict, platform: Platform, *, partial: bool = False) -> dict:
    """Validate manual or imported input and return SQLite-ready values."""
    source = dict(values)
    if "exposure" in source and _blank(source.get("views")):
        source["views"] = source["exposure"]
    normalized: dict = {"platform": platform.value}
    errors: dict[str, str] = {}
    for field in POST_FIELDS:
        if partial and field not in source:
            continue
        value = source.get(field)
        try:
            if field == "title":
                title = "" if value is None else str(value).strip()
                if not title:
                    raise ValueError("标题不能为空")
                normalized[field] = title
            elif field == "publish_time":
                raw_time = source.get("publish_time_raw")
                normalized[field] = _parse_datetime(value if not _blank(value) else raw_time)
            elif field == "publish_time_raw":
                normalized[field] = None if _blank(value) else str(value).strip()
            elif field == "content_source":
                if isinstance(value, ContentSource):
                    normalized[field] = value.value
                else:
                    normalized[field] = ContentSource("UNKNOWN" if _blank(value) else str(value).strip().upper()).value
            elif field in LIST_FIELDS:
                normalized[field] = _parse_string_list(value, field)
            elif field in METRIC_FIELDS or field == "duration":
                normalized[field] = _parse_number(value, field)
            else:
                normalized[field] = None if _blank(value) else str(value).strip()
        except (ValueError, TypeError) as exc:
            errors[field] = str(exc)
    if "title" not in normalized and not partial:
        errors["title"] = "标题不能为空"
    if errors:
        raise InvalidHistoricalPostError(errors)
    if not partial:
        normalized.setdefault("content_source", ContentSource.UNKNOWN.value)
        normalized.setdefault("tags", [])
        normalized.setdefault("subjects", [])
    return normalized


class HistoricalPostService:
    def __init__(self, repository: OperatorAccountRepository | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _to_model(row: dict) -> HistoricalPost:
        return HistoricalPost(
            id=row["id"], account_id=row["account_id"], platform=Platform(row["platform"]),
            publish_time=row["publish_time"], publish_time_raw=row.get("publish_time_raw"),
            title=row["title"], content_type=row["content_type"],
            content_source=ContentSource(row["content_source"]), tags=row["tags"], note=row["note"],
            duration=row["duration"], subjects=row["subjects"], hook_type=row["hook_type"],
            views=row["views"], likes=row["likes"], comments=row["comments"], favorites=row["favorites"],
            shares=row["shares"], followers_gain=row["followers_gain"], profile_visits=row["profile_visits"],
            inquiries=row["inquiries"], platform_post_id=row["platform_post_id"],
            data_source=row.get("data_source", "MANUAL"), source_updated_at=row.get("source_updated_at"),
            source_presence=row.get("source_presence", "PRESENT"), missing_since=row.get("missing_since"),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def _account_platform(self, account_id: str) -> Platform:
        try:
            return Platform(self.repository.get_account(account_id)["platform"])
        except AccountNotFoundError:
            raise

    def list_posts(self, account_id: str, *, offset: int = 0, limit: int = 100) -> list[HistoricalPost]:
        self._account_platform(account_id)
        return [self._to_model(row) for row in self.repository.list_posts(account_id, offset=offset, limit=limit)]

    def get_post(self, account_id: str, post_id: str) -> HistoricalPost:
        self._account_platform(account_id)
        row = self.repository.get_post(account_id, post_id)
        if row is None:
            raise LookupError(post_id)
        return self._to_model(row)

    def create_post(self, account_id: str, values: dict) -> HistoricalPost:
        platform = self._account_platform(account_id)
        values = ManualInputAdapter().adapt([values])[0]
        normalized = normalize_post(values, platform)
        normalized["account_id"] = account_id
        normalized["data_source"] = "MANUAL"
        normalized["source_updated_at"] = None
        post_id = str(uuid4())
        row = self.repository.create_post(post_id, normalized, self._now())
        if "duplicate_id" in row:
            raise DuplicateHistoricalPostError(row["duplicate_id"])
        return self._to_model(row)

    def update_post(self, account_id: str, post_id: str, values: dict) -> HistoricalPost:
        platform = self._account_platform(account_id)
        current = self.get_post(account_id, post_id)
        normalized = normalize_post(values, platform, partial=True)
        if "title" not in normalized:
            normalized["title"] = current.title
        row = self.repository.update_post(account_id, post_id, normalized, self._now())
        if row is None:
            raise LookupError(post_id)
        if "duplicate_id" in row:
            raise DuplicateHistoricalPostError(row["duplicate_id"])
        return self._to_model(row)

    def delete_post(self, account_id: str, post_id: str) -> None:
        self._account_platform(account_id)
        if not self.repository.delete_post(account_id, post_id):
            raise LookupError(post_id)

    def completeness(self, account_id: str) -> dict:
        platform = self._account_platform(account_id)
        posts = self.repository.list_posts(account_id, limit=100000)
        total = len(posts)
        reach_field = "views"
        interactions = ("likes", "comments", "favorites", "shares")
        ratios = {
            "publish_time": sum(row["publish_time"] is not None for row in posts),
            "content_type": sum(bool(row["content_type"]) for row in posts),
            "reach": sum(row[reach_field] is not None for row in posts),
            "interactions": sum(sum(row[field] is not None for field in interactions) >= 2 for row in posts),
        }
        coverage = {key: round(value / total, 4) if total else 0 for key, value in ratios.items()}
        score = (20 if total else 0) + 20 * coverage["publish_time"] + 20 * coverage["content_type"] \
                + 25 * coverage["reach"] + 15 * coverage["interactions"]
        return {
            "account_id": account_id,
            "platform": platform.value,
            "score": round(score),
            "sample_size": total,
            "coverage": coverage,
            "weights": {"has_posts": 20, "publish_time": 20, "content_type": 20, "views_or_exposure": 25,
                        "at_least_two_interaction_metrics": 15},
        }
