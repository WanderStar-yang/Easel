"""Preview-first full snapshot reconciliation and legacy duplicate repair."""

from __future__ import annotations

import json
import threading
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .historical import InvalidHistoricalPostError, normalize_post
from .models import Platform
from .repository import OperatorAccountRepository, clean_creator_center_title

PREVIEW_TTL = timedelta(minutes=30)
_METRIC_FIELDS = ("duration", "views", "likes", "comments", "favorites", "shares", "followers_gain")
_CLASSIFICATION_FIELDS = ("content_type", "content_source", "tags", "subjects", "hook_type", "note")


def _norm(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _time_key(value: object) -> str:
    raw = _norm(value).replace("/", "-").replace(".", "-")
    return raw[:19]


def stable_post_key(row: dict) -> str | None:
    post_id = _norm(row.get("platform_post_id"))
    if post_id:
        return f"id:{post_id}"
    title = _norm(clean_creator_center_title(str(row.get("title") or "")))
    publish_time = _time_key(row.get("publish_time"))
    if title and publish_time:
        return f"fingerprint:{publish_time}\0{title}"
    return None


def _legacy_title_key(row: dict) -> str | None:
    if row.get("platform_post_id") or row.get("publish_time"):
        return None
    if row.get("data_source") != "DOUYIN_CREATOR_CENTER":
        return None
    title = _norm(clean_creator_center_title(str(row.get("title") or "")))
    return f"legacy-title:{title}" if title else None


def _repair_key(row: dict) -> str | None:
    return stable_post_key(row) or _legacy_title_key(row)


def _completeness(row: dict) -> int:
    fields = ("platform_post_id", "publish_time", "publish_time_raw", "content_type", "duration", "views",
              "likes", "comments", "favorites", "shares", "followers_gain", "hook_type", "subjects", "tags")
    return sum(bool(row.get(key)) if key in {"subjects", "tags"} else row.get(key) is not None for key in fields)


def _has_value(field: str, value: object) -> bool:
    if field in {"subjects", "tags"}:
        return bool(value)
    if field == "content_source" and value == "UNKNOWN":
        return False
    return value is not None and value != ""


def _parse_time(row: dict) -> datetime:
    try:
        return datetime.fromisoformat((row.get("source_updated_at") or row.get("created_at") or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _merge_group(rows: list[dict], snapshot: dict | None, now: str) -> dict:
    ranked = sorted(rows, key=lambda row: (
        -int(bool(row.get("platform_post_id"))), -_completeness(row),
        -int(row.get("reference_count", 0)), row.get("created_at") or "\uffff", row.get("id") or "",
    ))
    canonical = dict(ranked[0])
    # Keep the earliest creation time when all higher-priority criteria tie.
    fields = set().union(*(row.keys() for row in rows))
    for field in fields:
        if field in {"id", "reference_count", "created_at", "updated_at", "source_updated_at", "source_presence", "missing_since"}:
            continue
        if _has_value(field, canonical.get(field)):
            continue
        for row in ranked[1:]:
            if _has_value(field, row.get(field)):
                canonical[field] = row[field]
                break
    # Metrics are facts from the newest observation, never max-aggregated.
    metric_rows = sorted(rows, key=lambda row: (_parse_time(row), row.get("created_at") or ""), reverse=True)
    for field in _METRIC_FIELDS:
        for row in metric_rows:
            if row.get(field) is not None:
                canonical[field] = row[field]
                break
    if snapshot:
        for field in ("platform_post_id", "title", "publish_time", "publish_time_raw", *_METRIC_FIELDS):
            value = snapshot.get(field)
            if value is not None and value != "":
                canonical[field] = value
    else:
        canonical["title"] = clean_creator_center_title(str(canonical.get("title") or ""))
    canonical["data_source"] = "DOUYIN_CREATOR_CENTER"
    canonical["source_updated_at"] = now if snapshot else max(
        (row.get("source_updated_at") for row in rows if row.get("source_updated_at")), default=None,
    )
    canonical["source_presence"] = "PRESENT"
    canonical["missing_since"] = None
    return canonical


class SnapshotReconciliationManager:
    def __init__(self, repository: OperatorAccountRepository):
        self.repository = repository
        self._previews: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _remember(self, account_id: str, kind: str, plan: dict, summary: dict) -> tuple[str, dict]:
        now = datetime.now(timezone.utc)
        preview_id = str(uuid4())
        with self._lock:
            self._previews = {key: item for key, item in self._previews.items()
                              if now - item["created_at"] <= PREVIEW_TTL}
            self._previews[preview_id] = {
                "account_id": account_id, "kind": kind, "plan": plan, "summary": summary,
                "created_at": now,
            }
        return preview_id, {"preview_id": preview_id, **summary}

    def _get_preview(self, account_id: str, preview_id: str, kind: str) -> dict:
        now = datetime.now(timezone.utc)
        with self._lock:
            preview = self._previews.get(preview_id)
            if not preview or now - preview["created_at"] > PREVIEW_TTL or preview["account_id"] != account_id or preview["kind"] != kind:
                self._previews.pop(preview_id, None)
                raise LookupError(preview_id)
            return preview

    def _existing(self, account_id: str) -> list[dict]:
        rows = self.repository.list_posts(account_id, limit=100000)
        refs = self.repository.post_reference_counts(account_id)
        for row in rows:
            row["reference_count"] = refs.get(row["id"], 0)
        return rows

    @staticmethod
    def _groups(rows: list[dict]) -> list[list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            key = _repair_key(row)
            if key:
                grouped.setdefault(key, []).append(row)
        return [items for items in grouped.values() if len(items) > 1]

    def preview_repair(self, account_id: str) -> dict:
        account = self.repository.get_account(account_id)
        if account["platform"] != Platform.DOUYIN.value:
            raise ValueError("历史重复修复仅适用于抖音账号")
        rows = self._existing(account_id)
        groups = self._groups(rows)
        id_map: dict[str, str] = {}
        merged_groups: list[dict] = []
        for group in groups:
            now = datetime.now(timezone.utc).isoformat()
            merged = _merge_group(group, None, now)
            canonical_id = merged["id"]
            duplicates = [row["id"] for row in group if row["id"] != canonical_id]
            id_map.update({post_id: canonical_id for post_id in duplicates})
            merged_groups.append({"canonical_id": canonical_id, "duplicate_ids": duplicates, "values": merged})
        summary = {
            "account_id": account_id,
            "database_current_count": len(rows),
            "duplicate_groups": len(groups),
            "duplicate_count": sum(len(group) - 1 for group in groups),
            "canonical_count_after_repair": len(rows) - sum(len(group) - 1 for group in groups),
            "reference_remap_count": len(id_map),
            "groups": [{"canonical_id": item["canonical_id"], "duplicate_ids": item["duplicate_ids"],
                        "title": clean_creator_center_title(item["values"].get("title") or ""),
                        "merged_fields": [key for key in (*_METRIC_FIELDS, *_CLASSIFICATION_FIELDS)
                                          if item["values"].get(key) not in (None, "", [], {})]}
                       for item in merged_groups[:200]],
            "preview_truncated": len(merged_groups) > 200,
        }
        plan = {"groups": merged_groups, "id_map": id_map,
                "base_versions": {row["id"]: row["updated_at"] for row in rows}}
        _, result = self._remember(account_id, "repair", plan, summary)
        return result

    def preview_snapshot(self, account_id: str, snapshot: list[dict], *, raw_count: int,
                         scan_duplicate_count: int, pages_scanned: int, expected_count: int | None,
                         scan_complete: bool) -> dict:
        account = self.repository.get_account(account_id)
        if account["platform"] != Platform.DOUYIN.value:
            raise ValueError("Creator Center Snapshot 仅适用于抖音账号")
        now = datetime.now(timezone.utc).isoformat()
        normalized: list[dict] = []
        errors: list[dict] = []
        seen: dict[str, dict] = {}
        for index, raw in enumerate(snapshot, 1):
            try:
                values = normalize_post(raw, Platform.DOUYIN)
            except InvalidHistoricalPostError as exc:
                errors.append({"row": index, "title": str(raw.get("title") or ""), "errors": exc.errors})
                continue
            values["account_id"] = account_id
            values["platform"] = Platform.DOUYIN.value
            values["data_source"] = "DOUYIN_CREATOR_CENTER"
            values["source_updated_at"] = now
            values.setdefault("publish_time_raw", raw.get("publish_time_raw"))
            key = stable_post_key(values)
            if key is None:
                errors.append({"row": index, "title": values.get("title"),
                               "errors": {"identity": "缺少作品 ID 或发布时间，无法建立稳定作品身份"}})
                continue
            if key in seen:
                # Nulls do not erase facts already read for this same item.
                for field, value in values.items():
                    if value is not None:
                        seen[key][field] = value
            else:
                seen[key] = values
        unique = list(seen.values())
        existing = self._existing(account_id)
        old_groups: dict[str, list[dict]] = {}
        for row in existing:
            key = _repair_key(row)
            if key:
                old_groups.setdefault(key, []).append(row)
        used_ids: set[str] = set()
        operations: list[dict] = []
        id_map: dict[str, str] = {}
        inserted = updated = backfilled = 0
        snapshot_title_counts = Counter(_norm(clean_creator_center_title(str(row.get("title") or ""))) for row in unique)
        for row in unique:
            key = stable_post_key(row)
            group = list(old_groups.get(key or "", []))
            legacy_key = _legacy_title_key({**row, "publish_time": None, "platform_post_id": None,
                                            "data_source": "DOUYIN_CREATOR_CENTER"})
            if legacy_key and snapshot_title_counts[_norm(clean_creator_center_title(str(row.get("title") or "")))] == 1:
                known = {item["id"] for item in group}
                group.extend(item for item in old_groups.get(legacy_key, []) if item["id"] not in known)
            if group:
                ranked = sorted(group, key=lambda item: (
                    -int(bool(item.get("platform_post_id"))), -_completeness(item),
                    -int(item.get("reference_count", 0)), item.get("created_at") or "\uffff",
                ))
                canonical_id = ranked[0]["id"]
                duplicates = [item["id"] for item in group if item["id"] != canonical_id]
                merged = _merge_group(group, row, now)
                merged["title"] = row["title"]
                merged["publish_time"] = row["publish_time"]
                merged["publish_time_raw"] = row.get("publish_time_raw") or merged.get("publish_time_raw")
                merged["platform_post_id"] = row.get("platform_post_id") or merged.get("platform_post_id")
                merged["id"] = canonical_id
                for duplicate_id in duplicates:
                    id_map[duplicate_id] = canonical_id
                    used_ids.add(duplicate_id)
                if ranked[0].get("publish_time") is None and row.get("publish_time"):
                    backfilled += 1
                if any(item.get("updated_at") != now for item in group):
                    updated += 1
                used_ids.update(item["id"] for item in group)
                operations.append({"canonical_id": canonical_id, "duplicate_ids": duplicates, "values": merged})
                if legacy_key:
                    old_groups.pop(legacy_key, None)
            else:
                inserted += 1
                operations.append({"canonical_id": None, "duplicate_ids": [], "values": row})
        missing = [row["id"] for row in existing if row["id"] not in used_ids and row.get("source_presence") != "MISSING"]
        complete = scan_complete and not errors and (expected_count is None or len(unique) == expected_count)
        summary = {
            "preview_kind": "snapshot", "snapshot_complete": complete,
            "platform_unique_count": len(unique), "database_current_count": len(existing),
            "insert_count": inserted, "update_count": updated,
            "scan_duplicate_count": max(scan_duplicate_count, raw_count - len(unique)),
            "historical_duplicate_count": sum(len(group) - 1 for group in self._groups(existing)),
            "platform_missing_count": len(missing), "publish_time_backfill_count": backfilled,
            "error_count": len(errors), "errors": errors[:100], "raw_observation_count": raw_count,
            "pages_scanned": pages_scanned, "expected_count": expected_count,
            "importable_count": inserted, "total_rows": raw_count, "duplicate_count": 0,
            "missing_fields": [], "headers": [], "rows": [], "preview_truncated": len(errors) > 100,
            "can_confirm": complete,
            "message": "扫描未完整到达作品列表末页或存在作品错误；不能执行快照对账。" if not complete else "完整快照就绪；确认后才会对账。",
        }
        plan = {"operations": operations, "missing_ids": missing,
                "base_versions": {row["id"]: row["updated_at"] for row in existing},
                "summary": summary}
        _, result = self._remember(account_id, "snapshot", plan, summary)
        return result

    def confirm(self, account_id: str, preview_id: str) -> dict:
        preview = self._get_preview(account_id, preview_id, "snapshot")
        if not preview["summary"].get("can_confirm"):
            raise ValueError("必须完成无错误的全量扫描后才能确认快照对账")
        result = self.repository.apply_snapshot_reconciliation(account_id, preview["plan"],
                                                                datetime.now(timezone.utc).isoformat())
        with self._lock:
            self._previews.pop(preview_id, None)
        return {**result, "data_source": "DOUYIN_CREATOR_CENTER"}

    def confirm_repair(self, account_id: str, preview_id: str) -> dict:
        preview = self._get_preview(account_id, preview_id, "repair")
        result = self.repository.apply_duplicate_repair(account_id, preview["plan"],
                                                        datetime.now(timezone.utc).isoformat())
        with self._lock:
            self._previews.pop(preview_id, None)
        return result
