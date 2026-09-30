"""Versioned account baselines calculated from canonical historical posts."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from uuid import uuid4

from .canonical import canonical_unique_posts
from .models import AccountBaseline
from .repository import AccountNotFoundError, OperatorAccountRepository
from .service import OperatorAccountService

BASELINE_ALGORITHM_VERSION = "account-baseline-v1"
MIN_GROUP_SAMPLE = 3
FORMAL_COMPARISON_SAMPLE = 5
METRIC_FIELDS = (
    "views", "likes", "comments", "favorites", "shares", "engagement_rate",
    "followers_gain", "profile_visits", "inquiries", "completion_rate",
    "two_sec_bounce_rate", "avg_watch_duration",
)
INTERACTION_FIELDS = ("likes", "comments", "favorites", "shares")


def _percentile(values: list[float | int], fraction: float) -> float | int | None:
    """Nearest-rank percentile; stable and easy to explain for small samples."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _engagement(row: dict) -> float | None:
    views = row.get("views")
    present = [row[field] for field in INTERACTION_FIELDS if row.get(field) is not None]
    if views is None or views <= 0 or not present:
        return None
    return sum(present) / views


def _duration_bucket(value: object) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    if value <= 15:
        return "≤15秒"
    if value <= 30:
        return "16–30秒"
    if value <= 60:
        return "31–60秒"
    return ">60秒"


def _publish_period(value: str | None) -> str | None:
    if not value:
        return None
    try:
        hour = datetime.fromisoformat(value.replace("Z", "+00:00")).hour
    except ValueError:
        return None
    if hour < 6:
        return "00–06"
    if hour < 12:
        return "06–12"
    if hour < 18:
        return "12–18"
    return "18–24"


def _metric_values(rows: list[dict]) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for field in METRIC_FIELDS:
        values: list[float | int]
        if field == "engagement_rate":
            values = [rate for row in rows if (rate := _engagement(row)) is not None]
        elif field in {"completion_rate", "two_sec_bounce_rate", "avg_watch_duration"}:
            # These are not parsed into HistoricalPost yet; null means unavailable.
            values = []
        else:
            values = [row[field] for row in rows if row.get(field) is not None]
        count = len(values)
        summary[field] = {
            "median": median(values) if values else None,
            "p25": _percentile(values, 0.25),
            "p75": _percentile(values, 0.75),
            "sample_count": count,
            "coverage": count / len(rows) if rows else 0,
        }
    return summary


def _dimension_value(row: dict, dimension: str) -> list[str]:
    if dimension == "content_source":
        source = row.get("content_source")
        return [source] if source and source != "UNKNOWN" else []
    if dimension == "content_type":
        value = str(row.get("content_type") or "").strip()
        return [value] if value and value.casefold() not in {"unknown", "未分类", "未知"} else []
    if dimension == "subjects":
        return sorted({str(value).strip() for value in (row.get("subjects") or [])
                       if str(value).strip() and str(value).strip().casefold() not in {"unknown", "未分类", "未知"}})
    if dimension == "hook_type":
        value = str(row.get("hook_type") or "").strip()
        return [value] if value and value.casefold() not in {"unknown", "未分类", "未知"} else []
    if dimension == "duration_bucket":
        bucket = _duration_bucket(row.get("duration"))
        return [bucket] if bucket else []
    if dimension == "publish_period":
        period = _publish_period(row.get("publish_time"))
        return [period] if period else []
    return []


def _segments(rows: list[dict]) -> dict[str, dict[str, object]]:
    dimensions = ("content_source", "content_type", "subjects", "hook_type", "duration_bucket", "publish_period")
    output: dict[str, dict[str, object]] = {}
    for dimension in dimensions:
        grouped: dict[str, list[dict]] = defaultdict(list)
        classified_posts: set[str] = set()
        for row in rows:
            keys = _dimension_value(row, dimension)
            if keys:
                classified_posts.add(row["id"])
                for key in keys:
                    grouped[key].append(row)
        output[dimension] = {
            "coverage": len(classified_posts) / len(rows) if rows else 0,
            "classified_sample_count": len(classified_posts),
            "groups": [
                {
                    "key": key,
                    "sample_size": len(group),
                    "metrics": _metric_values(group),
                    "eligible_for_comparison": len(group) >= FORMAL_COMPARISON_SAMPLE,
                }
                for key, group in sorted(grouped.items())
                if len(group) >= MIN_GROUP_SAMPLE
            ],
            "insufficient_group_count": sum(0 < len(group) < MIN_GROUP_SAMPLE for group in grouped.values()),
        }
    return output


def _data_version(rows: list[dict]) -> str:
    payload = [{key: row.get(key) for key in (
        "id", "updated_at", "publish_time", "title", "content_type", "content_source", "subjects",
        "hook_type", "duration", "views", "likes", "comments", "favorites", "shares", "followers_gain",
        "profile_visits", "inquiries", "source_presence",
    )} for row in rows]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AccountBaselineService:
    def __init__(self, repository: OperatorAccountRepository | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.accounts = OperatorAccountService(self.repository)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _source(self, account_id: str) -> tuple[list[dict], str, str | None, str | None]:
        self.accounts.get_account(account_id)
        raw = self.repository.list_posts(account_id, limit=100000)
        rows = canonical_unique_posts(raw)
        version = _data_version(rows)
        dates = sorted(row["publish_time"] for row in rows if row.get("publish_time"))
        source_dates = [row.get("source_updated_at") or row.get("updated_at") for row in rows]
        source_updated_at = max((value for value in source_dates if value), default=None)
        return rows, version, dates[0][:10] if dates else None, dates[-1][:10] if dates else None

    def preview(self, account_id: str) -> dict[str, object]:
        rows, version, period_start, period_end = self._source(account_id)
        if not rows:
            raise ValueError("暂无有效历史作品，无法建立历史基准。")
        diagnosis = self.repository.get_latest_diagnosis(account_id)
        if diagnosis is None:
            raise ValueError("请先完成有效的账号诊断，再建立历史基准。")
        if diagnosis.get("status") == "STALE":
            raise ValueError("当前账号诊断已过期，请先重新诊断。")
        metrics = _metric_values(rows)
        return {
            "sample_size": len(rows), "period_start": period_start, "period_end": period_end,
            "historical_data_version": version, "metrics": metrics,
            "classification_coverage": {key: value["coverage"] for key, value in _segments(rows).items()},
            "content_type_coverage": _segments(rows)["content_type"]["coverage"],
            "segments": _segments(rows),
            "metric_todo": ["完播率", "2秒跳出率", "平均播放时长"],
            "generated_at": self._now(),
        }

    def generate(self, account_id: str, expected_data_version: str | None = None) -> AccountBaseline:
        self.accounts.get_account(account_id)
        if expected_data_version:
            _, current_version, _, _ = self._source(account_id)
            if current_version != expected_data_version:
                raise ValueError("历史数据在预览后发生了变化，请重新预览。")
        preview = self.preview(account_id)
        if expected_data_version and expected_data_version != preview["historical_data_version"]:
            raise ValueError("历史数据在预览后发生了变化，请重新预览。")
        generated_at = self._now()
        rows, current_version, _, _ = self._source(account_id)
        if current_version != preview["historical_data_version"]:
            raise ValueError("历史数据在预览后发生了变化，请重新预览。")
        max_source_updated = max(
            (row.get("source_updated_at") or row.get("updated_at") for row in rows
             if row.get("source_updated_at") or row.get("updated_at")), default=None,
        )
        stored = self.repository.save_baseline(
            str(uuid4()), account_id, int(preview["sample_size"]), preview["period_start"],
            preview["period_end"], generated_at, max_source_updated, current_version,
            {"metrics": preview["metrics"], "segments": preview["segments"],
             "classification_coverage": preview["classification_coverage"],
             "metric_todo": preview["metric_todo"], "algorithm_version": BASELINE_ALGORITHM_VERSION},
        )
        return self._to_model(stored)

    def latest(self, account_id: str) -> AccountBaseline | None:
        self.accounts.get_account(account_id)
        row = self.repository.get_latest_baseline(account_id)
        if row is None:
            return None
        if row["status"] == "ACTIVE":
            _, version, _, _ = self._source(account_id)
            if version != row["historical_data_version"]:
                self.repository.mark_baseline_stale(account_id)
                row = self.repository.get_latest_baseline(account_id) or row
        return self._to_model(row)

    def history(self, account_id: str, limit: int = 20) -> list[AccountBaseline]:
        self.accounts.get_account(account_id)
        return [self._to_model(row) for row in self.repository.list_baselines(account_id, limit=limit)]

    def compare_to_baseline(self, account_id: str, metrics: dict[str, object]) -> dict[str, object]:
        baseline = self.latest(account_id)
        if baseline is None or baseline.status != "ACTIVE":
            raise ValueError("当前没有可用的历史基准，请先重新生成基准。")
        comparisons: dict[str, object] = {}
        for field in ("views", "likes", "engagement_rate"):
            observed = metrics.get(field)
            reference = baseline.metrics.get(field, {})
            center = reference.get("median") if isinstance(reference, dict) else None
            if not isinstance(observed, (int, float)) or not isinstance(center, (int, float)):
                comparisons[field] = {"value": observed, "baseline_median": center, "relative_change": None, "range": None}
                continue
            relative = (observed - center) / abs(center) if center else (0 if observed == 0 else None)
            low = reference.get("p25")
            high = reference.get("p75")
            band = "below_typical" if isinstance(low, (int, float)) and observed < low else (
                "above_typical" if isinstance(high, (int, float)) and observed > high else "typical"
            )
            comparisons[field] = {"value": observed, "baseline_median": center,
                                  "relative_change": relative, "range": band}
        return {"baseline_id": baseline.id, "baseline_version": baseline.version, "metrics": comparisons}

    @staticmethod
    def _to_model(row: dict) -> AccountBaseline:
        return AccountBaseline(
            id=row["id"], account_id=row["account_id"], version=row["version"], sample_size=row["sample_size"],
            period_start=row["period_start"], period_end=row["period_end"], generated_at=row["generated_at"],
            source_updated_at=row.get("source_updated_at"), historical_data_version=row["historical_data_version"],
            status=row["status"], metrics=row.get("metrics", {}), segments=row.get("segments", {}),
        )
