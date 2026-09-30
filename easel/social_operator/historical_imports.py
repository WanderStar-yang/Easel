"""Two-step CSV/XLSX preview and confirmation for historical posts."""

from __future__ import annotations

import io
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pandas as pd

from .historical import InvalidHistoricalPostError, HistoricalPostService, _blank, normalize_post
from .models import Platform
from .repository import OperatorAccountRepository
from .data_sources import FileImportAdapter

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
PREVIEW_TTL = timedelta(minutes=30)
PREVIEW_ROW_LIMIT = 100

_HEADER_ALIASES = {
    "publish_time": "publish_time", "publishtime": "publish_time", "published_at": "publish_time",
    "date": "publish_time", "发布时间": "publish_time", "发布日期": "publish_time",
    "title": "title", "name": "title", "作品标题": "title", "作品名称": "title", "标题": "title",
    "content_type": "content_type", "contenttype": "content_type", "内容类型": "content_type", "作品类型": "content_type", "体裁": "content_type",
    "content_source": "content_source", "contentsource": "content_source", "内容来源": "content_source",
    "source": "content_source", "tags": "tags", "tag": "tags", "标签": "tags",
    "note": "note", "备注": "note", "duration": "duration", "时长": "duration", "视频时长": "duration",
    "subjects": "subjects", "subject": "subjects", "主体": "subjects", "出镜主体": "subjects",
    "hook_type": "hook_type", "hooktype": "hook_type", "hook类型": "hook_type", "开头类型": "hook_type",
    "views": "views", "view": "views", "播放量": "views", "浏览量": "views", "曝光": "exposure",
    "exposure": "exposure", "likes": "likes", "like": "likes", "点赞": "likes", "点赞量": "likes",
    "comments": "comments", "comment": "comments", "评论": "comments", "评论量": "comments",
    "favorites": "favorites", "favorite": "favorites", "收藏": "favorites", "收藏量": "favorites",
    "shares": "shares", "share": "shares", "分享": "shares", "分享量": "shares",
    "followers_gain": "followers_gain", "followersgain": "followers_gain", "涨粉": "followers_gain", "新增粉丝": "followers_gain", "粉丝增量": "followers_gain",
    "profile_visits": "profile_visits", "profilevisits": "profile_visits", "主页访问": "profile_visits", "主页访问量": "profile_visits",
    "inquiries": "inquiries", "咨询": "inquiries", "私信咨询": "inquiries",
    "platform_post_id": "platform_post_id", "platformpostid": "platform_post_id", "作品id": "platform_post_id",
    "作品编号": "platform_post_id", "笔记id": "platform_post_id",
}


def _normalize_header(header: object) -> str:
    return "".join(char.lower() for char in str(header).strip() if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def _json_value(value):
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def read_import_file(filename: str, content: bytes) -> tuple[list[dict], list[str]]:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "csv":
        if not content.strip():
            return [], []
        text = None
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("CSV 编码无法识别，请使用 UTF-8 或 GB18030")
        try:
            frame = pd.read_csv(io.StringIO(text), dtype=object, keep_default_na=False)
        except pd.errors.EmptyDataError:
            return [], []
    elif suffix == "xlsx":
        if not content:
            return [], []
        try:
            frame = pd.read_excel(io.BytesIO(content), dtype=object, engine="openpyxl")
        except Exception as exc:  # parser messages differ by pandas/openpyxl version
            raise ValueError(f"XLSX 文件无法读取：{exc}") from exc
    else:
        raise ValueError("仅支持 .csv 与 .xlsx 文件")
    if len(frame.index) > MAX_IMPORT_ROWS:
        raise ValueError(f"单次导入最多支持 {MAX_IMPORT_ROWS} 行")
    return frame.to_dict(orient="records"), [str(column) for column in frame.columns]


@dataclass
class _Preview:
    account_id: str
    created_at: datetime
    records: list[dict]
    results: list[dict]
    summary: dict
    source: str = "FILE_IMPORT"


class HistoricalImportManager:
    """Holds uncommitted previews in memory; only confirm writes to SQLite."""

    def __init__(self, posts: HistoricalPostService, repository: OperatorAccountRepository):
        self.posts = posts
        self.repository = repository
        self._previews: dict[str, _Preview] = {}
        self._lock = threading.Lock()

    def _prune(self, now: datetime) -> None:
        stale = [key for key, preview in self._previews.items() if now - preview.created_at > PREVIEW_TTL]
        for key in stale:
            self._previews.pop(key, None)

    def preview(self, account_id: str, filename: str, content: bytes) -> tuple[str, dict]:
        if len(content) > MAX_IMPORT_BYTES:
            raise ValueError("文件不能超过 10 MB")
        raw_rows, headers = read_import_file(filename, content)
        adapted = FileImportAdapter().adapt(raw_rows)
        return self.preview_records(account_id, adapted, headers=headers, source=FileImportAdapter.source)

    def preview_records(self, account_id: str, raw_rows: list[dict], *, headers: list[str] | None = None,
                        source: str) -> tuple[str, dict]:
        platform = self.posts._account_platform(account_id)
        headers = headers if headers is not None else list(dict.fromkeys(key for row in raw_rows for key in row))
        rows: list[dict] = []
        results: list[dict] = []
        missing: Counter = Counter()
        missing_columns: set[str] = set()
        input_fields = {_HEADER_ALIASES.get(_normalize_header(header)) for header in headers}
        input_fields.discard(None)
        ignored_columns = [header for header in headers if _normalize_header(header) not in _HEADER_ALIASES]
        if "exposure" in input_fields:
            input_fields.add("views")
        required_metrics = ("publish_time", "content_type", "views", "likes", "comments", "favorites")
        missing_columns.update(field for field in required_metrics if field not in input_fields)
        seen_keys: set[tuple] = set()
        for index, raw in enumerate(raw_rows, start=2):
            mapped: dict = {}
            for header, value in raw.items():
                target = _HEADER_ALIASES.get(_normalize_header(header),
                                             header if header in {"platform_post_id", "publish_time", "title", "duration",
                                                                  "views", "play_count", "likes", "comments", "favorites", "shares"} else None)
                if target:
                    mapped[target] = value
            for field in required_metrics:
                if _blank(mapped.get(field)):
                    missing[field] += 1
            errors: dict[str, str] = {}
            normalized: dict = {}
            try:
                normalized = normalize_post(mapped, platform)
            except InvalidHistoricalPostError as exc:
                errors.update(exc.errors)
            normalized["account_id"] = account_id
            normalized["platform"] = platform.value
            normalized["data_source"] = source
            normalized["source_updated_at"] = datetime.now(timezone.utc).isoformat() if source != "MANUAL" else None
            duplicate_id = None
            if not errors:
                if normalized.get("platform_post_id"):
                    key = ("platform_post_id", normalized["platform_post_id"])
                elif normalized.get("publish_time") and normalized.get("title"):
                    key = ("post", normalized["publish_time"], normalized["title"].strip().casefold())
                else:
                    key = None
                if key and key in seen_keys:
                    duplicate_id = "本文件前面的重复行"
                elif key:
                    seen_keys.add(key)
                    duplicate_id = self.repository.find_duplicate(normalized)
            status = "invalid" if errors else (
                "duplicate" if duplicate_id else "ready"
            )
            rows.append(normalized if not errors else mapped)
            results.append({
                "row": index,
                "status": status,
                "errors": errors,
                "duplicate_of": duplicate_id,
                "record": {key: _json_value(value) for key, value in (normalized if not errors else mapped).items()},
            })
        summary = {
            "total_rows": len(raw_rows),
            "scanned_count": len(raw_rows),
            "importable_count": sum(result["status"] == "ready" for result in results),
            "update_count": sum(result["status"] == "update" for result in results),
            "error_count": sum(result["status"] == "invalid" for result in results),
            "duplicate_count": sum(result["status"] == "duplicate" for result in results),
            "missing_fields": [
                {"field": field, "missing_rows": missing[field], "column_missing": field in missing_columns}
                for field in required_metrics if missing[field] or field in missing_columns
            ],
            "headers": headers,
            "ignored_columns": ignored_columns,
            "rows": results[:PREVIEW_ROW_LIMIT],
            "preview_truncated": len(results) > PREVIEW_ROW_LIMIT,
        }
        now = datetime.now(timezone.utc)
        preview_id = str(uuid4())
        with self._lock:
            self._prune(now)
            self._previews[preview_id] = _Preview(account_id, now, rows, results, summary, source)
        return preview_id, summary

    def confirm(self, account_id: str, preview_id: str) -> dict:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._prune(now)
            preview = self._previews.get(preview_id)
            if preview is None or preview.account_id != account_id:
                raise LookupError(preview_id)
            valid_rows = [
                (str(uuid4()), row)
                for row, result in zip(preview.records, preview.results)
                if result["status"] in {"ready", "update"}
            ]
            for _, row in valid_rows:
                row.setdefault("data_source", preview.source)
                row.setdefault("source_updated_at", now.isoformat())
            inserted, duplicates = self.repository.create_posts(valid_rows, now.isoformat())
            inserted_count = len(inserted)
            duplicate_count = len(duplicates) + preview.summary["duplicate_count"]
            updated_count = 0
            self._previews.pop(preview_id, None)
        return {
            "imported_count": inserted_count,
            "updated_count": updated_count,
            "skipped_duplicate_count": duplicate_count,
            "error_count": preview.summary["error_count"],
            "scanned_count": preview.summary["scanned_count"],
            "data_source": preview.source,
            "last_sync_at": None,
        }
