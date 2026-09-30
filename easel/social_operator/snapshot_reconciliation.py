"""Preview-first official-export reconciliation and legacy duplicate repair."""

from __future__ import annotations

import threading
import unicodedata
from hashlib import sha256
from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .historical import InvalidHistoricalPostError, normalize_post
from .historical_imports import _json_value
from .models import Platform
from .repository import OperatorAccountRepository, clean_legacy_scan_title

PREVIEW_TTL = timedelta(minutes=30)
OFFICIAL_EXPORT_SOURCE = "DOUYIN_OFFICIAL_EXPORT"
_METRIC_FIELDS = ("duration", "views", "likes", "comments", "favorites", "shares", "followers_gain")
_CLASSIFICATION_FIELDS = ("content_type", "content_type_raw", "content_source", "tags", "subjects", "hook_type", "note")


def _norm(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _time_key(value: object) -> str:
    raw = _norm(value).replace("/", "-").replace(".", "-")
    return raw[:19]


def stable_post_key(row: dict) -> str | None:
    post_id = _norm(row.get("platform_post_id"))
    if post_id:
        return f"id:{post_id}"
    title = _norm(clean_legacy_scan_title(str(row.get("title") or "")))
    publish_time = _time_key(row.get("publish_time"))
    if title and publish_time:
        return f"fingerprint:{publish_time}\0{title}"
    return None


def _low_confidence_key(row: dict) -> str | None:
    """A conservative title/type fingerprint used only when ID and date are absent."""
    title = _norm(clean_legacy_scan_title(str(row.get("title") or "")))
    if not title:
        return None
    content_type = _norm(row.get("content_type_raw"))
    return f"weak:{title}\0{content_type}"


def _legacy_title_key(row: dict) -> str | None:
    if row.get("platform_post_id") or row.get("publish_time"):
        return None
    # Keep compatibility with rows created by the retired browser importer.
    if row.get("data_source") != "DOUYIN_CREATOR_CENTER":
        return None
    title = _norm(clean_legacy_scan_title(str(row.get("title") or "")))
    return f"legacy-title:{title}" if title else None


def _cross_source_title_key(row: dict, *, legacy: bool) -> str | None:
    title = clean_legacy_scan_title(str(row.get("title") or "")) if legacy else str(row.get("title") or "")
    # Creator Center captured line wrapping inconsistently; whitespace is not
    # part of a title identity when a complete official export supplies the
    # corresponding uniquely titled post.
    title = "".join(unicodedata.normalize("NFKC", title).split()).casefold()
    return title or None


def _repair_key(row: dict) -> str | None:
    return (stable_post_key(row) or _legacy_title_key(row)
            or (_low_confidence_key(row) if row.get("data_source") == OFFICIAL_EXPORT_SOURCE else None))


def _identity_confidence(row: dict) -> str:
    if _norm(row.get("platform_post_id")):
        return "high"
    if row.get("publish_time"):
        return "medium"
    return "low"


def _completeness(row: dict) -> int:
    fields = ("platform_post_id", "publish_time", "publish_time_raw", "content_type", "content_type_raw",
              "duration", "views", "likes", "comments", "favorites", "shares", "followers_gain",
              "hook_type", "subjects", "tags")
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
    # Dynamic metrics come from the latest observed row, never from max().
    metric_rows = sorted(rows, key=lambda row: (_parse_time(row), row.get("created_at") or ""), reverse=True)
    for field in _METRIC_FIELDS:
        for row in metric_rows:
            if row.get(field) is not None:
                canonical[field] = row[field]
                break
    if snapshot:
        for field in ("platform_post_id", "title", "publish_time", "publish_time_raw", "content_type_raw", *_METRIC_FIELDS):
            value = snapshot.get(field)
            if value is not None and value != "":
                canonical[field] = value
        canonical["data_source"] = snapshot.get("data_source") or OFFICIAL_EXPORT_SOURCE
    else:
        canonical["title"] = clean_legacy_scan_title(str(canonical.get("title") or ""))
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
            if (not preview or now - preview["created_at"] > PREVIEW_TTL
                    or preview["account_id"] != account_id or preview["kind"] != kind):
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
        official_by_title: dict[str, list[dict]] = {}
        for row in rows:
            if row.get("data_source") == OFFICIAL_EXPORT_SOURCE:
                key = _cross_source_title_key(row, legacy=False)
                if key:
                    official_by_title.setdefault(key, []).append(row)
        cross_source_groups: list[list[dict]] = []
        consumed: set[str] = set()
        legacy_by_title: dict[str, list[dict]] = {}
        for row in rows:
            if row.get("data_source") != "DOUYIN_CREATOR_CENTER":
                continue
            key = _cross_source_title_key(row, legacy=True)
            if key:
                legacy_by_title.setdefault(key, []).append(row)
        for key, legacy_rows in legacy_by_title.items():
            official_rows = official_by_title.get(key, [])
            if len(official_rows) != 1:
                continue
            official = official_rows[0]
            group = [official, *legacy_rows]
            merged = _merge_group(group, None, datetime.now(timezone.utc).isoformat())
            # The official export is authoritative for platform facts and owns
            # the canonical ID; legacy scan rows can only fill fields it lacks.
            merged["id"] = official["id"]
            merged["title"] = official["title"]
            for field in ("platform_post_id", "publish_time", "publish_time_raw", "content_type_raw",
                          *_METRIC_FIELDS, "source_updated_at", "data_source", "source_presence", "missing_since"):
                if official.get(field) not in (None, ""):
                    merged[field] = official[field]
            duplicates = [row["id"] for row in group if row["id"] != official["id"]]
            cross_source_groups.append(group)
            consumed.update(row["id"] for row in group)
        remaining_groups = self._groups([row for row in rows if row["id"] not in consumed])
        all_groups = [*cross_source_groups, *remaining_groups]
        auto_groups = [group for group in all_groups if stable_post_key(group[0])]
        manual_groups = [group for group in all_groups if not stable_post_key(group[0])]
        merged_groups: list[dict] = []
        id_map: dict[str, str] = {}
        for group in auto_groups:
            merged = _merge_group(group, None, datetime.now(timezone.utc).isoformat())
            official = next((row for row in group if row.get("data_source") == OFFICIAL_EXPORT_SOURCE), None)
            canonical_id = official["id"] if official else merged["id"]
            if official:
                merged["id"] = canonical_id
                merged["title"] = official["title"]
                for field in ("platform_post_id", "publish_time", "publish_time_raw", "content_type_raw",
                              *_METRIC_FIELDS, "source_updated_at", "data_source", "source_presence", "missing_since"):
                    if official.get(field) not in (None, ""):
                        merged[field] = official[field]
                merged["source_presence"] = "PRESENT"
            duplicates = [row["id"] for row in group if row["id"] != canonical_id]
            id_map.update({post_id: canonical_id for post_id in duplicates})
            merged_groups.append({"canonical_id": canonical_id, "duplicate_ids": duplicates, "values": merged})
        duplicate_count = sum(len(group) - 1 for group in all_groups)
        auto_count = sum(len(group) - 1 for group in auto_groups)
        manual_count = sum(len(group) - 1 for group in manual_groups)
        estimated_unique = len(rows) - duplicate_count
        manual_plans = []
        manual_summaries = []
        for group in manual_groups:
            post_ids = sorted(row["id"] for row in group)
            group_id = sha256("\0".join(post_ids).encode()).hexdigest()[:16]
            merged = _merge_group(group, None, datetime.now(timezone.utc).isoformat())
            canonical_id = merged["id"]
            duplicates = [row["id"] for row in group if row["id"] != canonical_id]
            manual_plans.append({"group_id": group_id, "canonical_id": canonical_id,
                                 "duplicate_ids": duplicates, "values": merged})
            manual_summaries.append({
                "group_id": group_id,
                "title": clean_legacy_scan_title(group[0].get("title") or ""),
                "post_ids": post_ids,
                "count": len(group),
            })
        summary = {
            "account_id": account_id,
            "database_current_count": len(rows),
            "estimated_unique_count": estimated_unique,
            "duplicate_groups": len(all_groups),
            "duplicate_count": duplicate_count,
            "auto_merge_count": auto_count,
            "manual_review_count": manual_count,
            "canonical_count_after_repair": len(rows) - auto_count,
            "reference_remap_count": len(id_map),
            "groups": [{"canonical_id": item["canonical_id"], "duplicate_ids": item["duplicate_ids"],
                        "title": clean_legacy_scan_title(item["values"].get("title") or ""),
                        "merged_fields": [key for key in (*_METRIC_FIELDS, *_CLASSIFICATION_FIELDS)
                                          if item["values"].get(key) not in (None, "", [], {})]}
                       for item in merged_groups[:200]],
            "manual_review_groups": manual_summaries[:200],
            "preview_truncated": len(merged_groups) > 200 or len(manual_groups) > 200,
        }
        plan = {"groups": merged_groups, "manual_groups": manual_plans, "id_map": id_map,
                "base_versions": {row["id"]: row["updated_at"] for row in rows}}
        _, result = self._remember(account_id, "repair", plan, summary)
        return result

    def preview_snapshot(self, account_id: str, snapshot: list[dict], *, headers: list[str],
                         unsupported_columns: list[str], missing_columns: list[str],
                         source: str = OFFICIAL_EXPORT_SOURCE) -> dict:
        account = self.repository.get_account(account_id)
        if account["platform"] != Platform.DOUYIN.value:
            raise ValueError("抖音官方作品列表快照仅适用于抖音账号")
        now = datetime.now(timezone.utc).isoformat()
        seen: dict[str, dict] = {}
        row_results: list[dict] = []
        errors: list[dict] = []
        low_confidence_rows = 0
        for index, raw in enumerate(snapshot, 2):
            try:
                values = normalize_post(raw, Platform.DOUYIN)
            except InvalidHistoricalPostError as exc:
                errors.append({"row": index, "title": str(raw.get("title") or ""), "errors": exc.errors})
                row_results.append({"row": index, "status": "invalid", "errors": exc.errors,
                                    "record": {key: _json_value(value) for key, value in raw.items()
                                               if key != "data_source"}})
                continue
            values.update({"account_id": account_id, "platform": Platform.DOUYIN.value,
                           "data_source": source, "source_updated_at": now})
            key = stable_post_key(values)
            if key is None:
                key = _low_confidence_key(values)
                low_confidence_rows += 1
            if key is None:
                errors.append({"row": index, "title": values.get("title") or "",
                               "errors": {"title": "缺少可用于作品识别的标题"}})
                row_results.append({"row": index, "status": "invalid", "errors": {"title": "标题不能为空"},
                                    "record": values})
                continue
            if key in seen:
                previous = seen[key]
                for field, value in values.items():
                    if value is not None and value != "":
                        previous["record"][field] = value
                previous["duplicate_count"] += 1
            else:
                seen[key] = {"record": values, "source_rows": [index], "duplicate_count": 0}
        unique = [item["record"] for item in seen.values()]
        duplicate_count = len(snapshot) - len(unique)
        existing = self._existing(account_id)
        old_groups: dict[str, list[dict]] = {}
        old_by_title: dict[str, list[dict]] = {}
        for row in existing:
            key = _repair_key(row)
            if key:
                old_groups.setdefault(key, []).append(row)
            title_key = _norm(clean_legacy_scan_title(row.get("title") or ""))
            if title_key:
                old_by_title.setdefault(title_key, []).append(row)
        snapshot_titles = Counter(_norm(row.get("title") or "") for row in unique)
        used_ids: set[str] = set()
        operations: list[dict] = []
        operation_actions: dict[int, str] = {}
        id_map: dict[str, str] = {}
        inserted = updated = backfilled = 0
        for row in unique:
            key = stable_post_key(row)
            match_key = key or _low_confidence_key(row)
            group = list(old_groups.get(match_key or "", []))
            if not key and len(group) > 1:
                message = "低置信度作品指纹匹配到多条历史记录；请先在历史修复中逐组确认。"
                errors.append({"row": next((item["source_rows"][0] for item in seen.values()
                                             if item["record"] is row), 0),
                               "title": row.get("title") or "", "errors": {"identity": message}})
                row_results.append({"row": next((item["source_rows"][0] for item in seen.values()
                                                  if item["record"] is row), 0),
                                    "status": "invalid", "errors": {"identity": message}, "record": row})
                continue
            if not group and not key:
                title_key = _norm(row.get("title") or "")
                title_candidates = [candidate for candidate in old_by_title.get(title_key, [])
                                    if candidate.get("data_source") == "DOUYIN_CREATOR_CENTER"]
                if snapshot_titles[title_key] == 1 and len(title_candidates) == 1:
                    group = list(title_candidates)
            if group:
                ranked = sorted(group, key=lambda item: (
                    -int(bool(item.get("platform_post_id"))), -_completeness(item),
                    -int(item.get("reference_count", 0)), item.get("created_at") or "\uffff",
                ))
                canonical_id = ranked[0]["id"]
                duplicates = [item["id"] for item in group if item["id"] != canonical_id]
                merged = _merge_group(group, row, now)
                merged["id"] = canonical_id
                for duplicate_id in duplicates:
                    id_map[duplicate_id] = canonical_id
                if ranked[0].get("publish_time") is None and row.get("publish_time"):
                    backfilled += 1
                updated += 1
                used_ids.update(item["id"] for item in group)
                operations.append({"canonical_id": canonical_id, "duplicate_ids": duplicates, "values": merged})
                operation_actions[id(row)] = "update"
            else:
                inserted += 1
                operations.append({"canonical_id": None, "duplicate_ids": [], "values": row})
                operation_actions[id(row)] = "ready"

        for item in seen.values():
            record = item["record"]
            row_results.append({"row": item["source_rows"][0],
                                "status": operation_actions.get(id(record), "ready"), "errors": {},
                                "duplicate_count": item["duplicate_count"], "record": record})

        identity_confidence = "low" if low_confidence_rows else (
            "high" if unique and all(_identity_confidence(row) == "high" for row in unique) else "medium"
        )
        reconcile_missing = identity_confidence != "low" and not errors
        missing = [row["id"] for row in existing
                   if reconcile_missing and row["id"] not in used_ids and row.get("source_presence") != "MISSING"]
        complete = not errors
        missing_fields = []
        for field in ("publish_time", "content_type_raw", "views", "likes", "comments", "favorites"):
            column_missing = field in missing_columns
            missing_rows = sum(1 for row in unique if row.get(field) in (None, ""))
            if column_missing or missing_rows:
                missing_fields.append({"field": field, "missing_rows": missing_rows, "column_missing": column_missing})
        warnings = []
        if "publish_time" in missing_columns:
            warnings.append("发布时间：导出文件未提供；不会用当前时间填充。")
        elif any(row.get("publish_time") is None for row in unique):
            warnings.append("部分作品缺少发布时间；将保留空值，不会用当前时间填充。")
        if identity_confidence == "low":
            warnings.append("当前导出文件缺少稳定作品 ID 和部分发布时间，重复匹配置信度较低；本次不会标记数据库记录缺失。")
        summary = {
            "preview_kind": "snapshot", "snapshot_complete": complete, "can_confirm": complete,
            "detected_platform": "抖音创作者中心", "source": source,
            "file_record_count": len(snapshot), "platform_unique_count": len(unique),
            "database_current_count": len(existing), "insert_count": inserted, "update_count": updated,
            "duplicate_count": duplicate_count,
            "historical_duplicate_count": sum(len(group) - 1 for group in self._groups(existing)),
            "platform_missing_count": len(missing), "publish_time_backfill_count": backfilled,
            "error_count": len(errors), "errors": errors[:100], "unsupported_columns": unsupported_columns,
            "identity_confidence": identity_confidence, "warnings": warnings,
            "missing_fields": missing_fields, "headers": headers,
            "rows": row_results[:100], "preview_truncated": len(row_results) > 100 or len(errors) > 100,
            "total_rows": len(snapshot), "scanned_count": len(snapshot), "importable_count": inserted,
            "update_count": updated, "raw_observation_count": len(snapshot), "unique_count": len(unique),
            "scan_duplicate_count": duplicate_count,
            "message": "文件已解析；检查预览后确认官方导出快照。" if complete else "存在错误行，修正文件后再确认完整快照。",
        }
        plan = {"operations": operations, "missing_ids": missing,
                "base_versions": {row["id"]: row["updated_at"] for row in existing},
                "summary": summary}
        _, result = self._remember(account_id, "snapshot", plan, summary)
        return result

    def confirm(self, account_id: str, preview_id: str) -> dict:
        preview = self._get_preview(account_id, preview_id, "snapshot")
        if not preview["summary"].get("can_confirm"):
            raise ValueError("存在错误行，修正导出文件后重新生成预览")
        result = self.repository.apply_snapshot_reconciliation(
            account_id, preview["plan"], datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._previews.pop(preview_id, None)
        return {**result, "data_source": OFFICIAL_EXPORT_SOURCE}

    def confirm_repair(self, account_id: str, preview_id: str, manual_group_ids: list[str] | None = None) -> dict:
        preview = self._get_preview(account_id, preview_id, "repair")
        selected = set(manual_group_ids or [])
        valid_ids = {group["group_id"] for group in preview["plan"].get("manual_groups", [])}
        if not selected.issubset(valid_ids):
            raise ValueError("人工确认的重复组不属于当前预览")
        plan = dict(preview["plan"])
        plan["groups"] = [*plan["groups"], *[
            {key: value for key, value in group.items() if key != "group_id"}
            for group in plan.get("manual_groups", []) if group["group_id"] in selected
        ]]
        result = self.repository.apply_duplicate_repair(
            account_id, plan, datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._previews.pop(preview_id, None)
        return {**result, "manual_review_confirmed": len(selected)}
