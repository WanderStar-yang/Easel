"""Canonical, account-scoped views of historical posts for analysis and UI."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

_CREATOR_UI = re.compile(r"(?:\s*(?:编辑作品|设置权限|作品置顶|取消置顶|置顶|删除作品))+\s*$")


def clean_title(title: str | None) -> str:
    """Remove creator-center action labels accidentally appended by legacy scans."""
    value = unicodedata.normalize("NFKC", str(title or ""))
    previous = None
    while previous != value:
        previous = value
        value = _CREATOR_UI.sub("", value)
    return " ".join(value.split()).strip()


def _normal(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def post_fingerprint(row: dict) -> str | None:
    post_id = _normal(row.get("platform_post_id"))
    if post_id:
        return f"id:{post_id}"
    title = _normal(clean_title(row.get("title")))
    published = _normal(row.get("publish_time"))
    if title and published:
        return f"post:{published}\0{title}"
    return None


def canonical_unique_posts(rows: list[dict], *, current_only: bool = True) -> list[dict]:
    """Deduplicate stable identities before any statistical operation.

    Rows without a platform ID or publish-time/title fingerprint are preserved
    as unverified records rather than silently merged by title alone.
    """
    candidates = [row for row in rows if not current_only or row.get("source_presence", "PRESENT") != "MISSING"]
    groups: dict[str, list[dict]] = defaultdict(list)
    unkeyed: list[dict] = []
    for row in candidates:
        key = post_fingerprint(row)
        (groups[key] if key else unkeyed).append(row)

    def quality(row: dict) -> tuple[int, int, str]:
        source = row.get("data_source")
        source_priority = 3 if source == "DOUYIN_OFFICIAL_EXPORT" else 2 if source in ("FILE_IMPORT", "MANUAL") else 1
        filled = sum(row.get(field) not in (None, "", [], {}) for field in (
            "publish_time", "content_type", "views", "likes", "comments", "favorites", "shares", "duration",
        ))
        return source_priority, filled, str(row.get("updated_at") or "")

    unique = [max(group, key=quality) for group in groups.values()] + unkeyed
    for row in unique:
        row["title"] = clean_title(row.get("title"))
    return sorted(unique, key=lambda row: (
        row.get("publish_time") is None, row.get("publish_time") or "", row.get("id") or "",
    ), reverse=True)


def suspected_duplicate_count(rows: list[dict]) -> int:
    """Count repeated stable or legacy-title keys for diagnostic detail only."""
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        key = post_fingerprint(row)
        if key is None and row.get("data_source") == "DOUYIN_CREATOR_CENTER":
            title = _normal(clean_title(row.get("title")))
            key = f"legacy-title:{title}" if title else None
        if key:
            counts[key] += 1
    return sum(count - 1 for count in counts.values() if count > 1)
