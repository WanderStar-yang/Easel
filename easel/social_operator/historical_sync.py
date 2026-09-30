"""Persistent, account-scoped sessions for explicitly initiated local browser sync."""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from urllib.parse import urlparse

from .repository import OperatorAccountRepository

SESSION_TTL = timedelta(days=7)
SYNC_STATES = {
    "extension_unavailable", "extension_available", "creator_tab_not_found", "not_logged_in",
    "unsupported_page", "ready_to_scan", "scanning", "paused", "scan_completed", "scan_failed",
    "ended", "cancelled", "preview_ready", "pause_requested", "resume_requested", "end_requested",
}


def _normalized_text(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _normalized_date(value: object) -> str:
    text = _normalized_text(value).replace("/", "-").replace(".", "-")
    chinese = re.fullmatch(r"(20\d{2})年(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{2}))?", text)
    if chinese:
        year, month, day, hour, minute = chinese.groups()
        return f"{year}-{int(month):02d}-{int(day):02d} {int(hour or 0):02d}:{int(minute or 0):02d}"
    return text[:16].strip()


def _record_key(row: dict) -> str | None:
    platform_id = _normalized_text(row.get("platform_post_id"))
    if platform_id:
        return f"id:{platform_id}"
    title = _normalized_text(row.get("title"))
    publish_time = _normalized_date(row.get("publish_time") or row.get("publish_time_raw"))
    if title and publish_time:
        return f"composite:{publish_time}\0{title}"
    return f"title:{title}" if title else None


class HistoricalSyncSessionManager:
    def __init__(self, repository: OperatorAccountRepository | None = None) -> None:
        self.repository = repository
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def validate_creator_center_url(source_url: str) -> bool:
        parsed = urlparse(source_url)
        return parsed.scheme == "https" and parsed.hostname == "creator.douyin.com"

    def create(self, account_id: str) -> dict:
        now = self._now()
        session_id = token_urlsafe(32)
        session = {
            "session_id": session_id, "account_id": account_id, "created_at": now.isoformat(),
            "updated_at": now.isoformat(), "expires_at": (now + SESSION_TTL).isoformat(),
            "preview_id": None, "summary": None, "status": "extension_unavailable",
            "extension_available": False, "message": "等待浏览器辅助扩展连接", "source_url": "",
            "scan_rows": [], "raw_observation_count": 0, "unique_count": 0, "duplicate_count": 0,
            "pages_scanned": 0, "last_page_fingerprint": None, "next_page_hint": None, "expected_count": None,
        }
        if self.repository:
            self.repository.create_sync_session({key: value for key, value in session.items()
                                                  if key in {"session_id", "account_id", "status", "message",
                                                             "created_at", "updated_at", "expires_at"}})
        else:
            with self._lock:
                self._sessions[session_id] = session
        return self._public(session)

    @staticmethod
    def _public(session: dict) -> dict:
        result = {key: value for key, value in session.items() if key != "scan_rows"}
        result["unique_count"] = len(session.get("scan_rows", []))
        result["seen_post_ids"] = sorted({str(row["platform_post_id"]) for row in session.get("scan_rows", [])
                                           if row.get("platform_post_id")})
        result["last_seen_at"] = session.get("updated_at")
        result["has_more"] = bool(session.get("next_page_hint")) and session["status"] not in {"ended", "cancelled"}
        result["status"] = "preview_ready" if session.get("preview_id") else session["status"]
        result["preview"] = session.get("summary")
        return result

    def _get(self, account_id: str, session_id: str) -> dict | None:
        if self.repository:
            return self.repository.get_sync_session(account_id, session_id)
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session["account_id"] != account_id:
                return None
            if datetime.fromisoformat(session["expires_at"]) <= self._now():
                self._sessions.pop(session_id, None)
                return None
            return dict(session)

    def _update(self, account_id: str, session_id: str, values: dict) -> dict | None:
        now = self._now().isoformat()
        values = {**values, "updated_at": now}
        if "scan_rows" in values:
            values["scan_rows_json"] = json.dumps(values.pop("scan_rows"), ensure_ascii=False)
        if "summary" in values:
            summary = values.pop("summary")
            values["summary_json"] = json.dumps(summary, ensure_ascii=False) if summary is not None else None
        if self.repository:
            return self.repository.update_sync_session(account_id, session_id, values)
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session["account_id"] != account_id:
                return None
            if "scan_rows_json" in values:
                values["scan_rows"] = json.loads(values.pop("scan_rows_json"))
            if "summary_json" in values:
                values["summary"] = json.loads(values.pop("summary_json")) if values["summary_json"] else None
            session.update(values)
            session["unique_count"] = len(session["scan_rows"])
            return dict(session)

    def list(self, account_id: str) -> list[dict]:
        if self.repository:
            sessions = self.repository.list_sync_sessions(account_id)
        else:
            with self._lock:
                sessions = [dict(row) for row in self._sessions.values() if row["account_id"] == account_id]
        return [self._public(session) for session in sessions]

    def get(self, account_id: str, session_id: str) -> dict:
        session = self._get(account_id, session_id)
        if session is None:
            raise LookupError(session_id)
        return self._public(session)

    def report_state(self, account_id: str, session_id: str, status: str, message: str = "",
                     source_url: str = "") -> dict:
        if status not in SYNC_STATES - {"preview_ready", "pause_requested", "resume_requested", "end_requested"}:
            raise ValueError("不支持的同步状态")
        if source_url and not self.validate_creator_center_url(source_url):
            raise PermissionError("扩展状态只接受抖音创作者中心页面")
        session = self._update(account_id, session_id, {
            "status": status, "extension_available": True, "message": message[:300],
            "source_url": source_url or (self._get(account_id, session_id) or {}).get("source_url", ""),
        })
        if session is None:
            raise LookupError(session_id)
        return self.get(account_id, session_id)

    def control(self, account_id: str, session_id: str, action: str) -> dict:
        states = {"pause": "pause_requested", "resume": "resume_requested", "end": "end_requested",
                  "cancel": "cancelled"}
        if action not in states:
            raise ValueError("不支持的同步操作")
        session = self._get(account_id, session_id)
        if session is None:
            raise LookupError(session_id)
        if action == "end" and session["status"] == "scan_completed":
            # A completed scan has already saved its final checkpoint. Ending it
            # should preserve the terminal state so the caller can preview it.
            return self._public(session)
        if session["status"] in {"cancelled", "ended", "preview_ready"}:
            raise ValueError("当前同步会话不能再控制")
        target = states[action]
        if action == "end" and session["status"] in {
            "extension_unavailable", "extension_available", "creator_tab_not_found", "not_logged_in",
            "unsupported_page", "ready_to_scan", "paused", "scan_failed",
        }:
            # No scanner loop is active in these states, so the saved checkpoint
            # can be closed immediately instead of waiting for a worker to ack.
            target = "ended"
        if action == "resume" and session["status"] not in {
            "paused", "pause_requested", "scan_failed", "resume_requested", "scanning",
        }:
            raise ValueError("只有未完成或失败的扫描可以继续")
        updated = self._update(account_id, session_id, {
            "status": target, "message": {"pause": "已请求暂停，将在当前页扫描保存后暂停",
                                            "resume": "已请求继续扫描",
            "end": "已结束扫描，可预览已保存作品" if target == "ended" else "已请求结束扫描，可生成当前结果预览",
                                            "cancel": "扫描已取消"}[action],
            "next_page_hint": None if action == "cancel" else session.get("next_page_hint"),
        })
        if updated is None:
            raise LookupError(session_id)
        return self.get(account_id, session_id)

    def checkpoint(self, account_id: str, session_id: str, rows: list[dict], source_url: str,
                   *, page_fingerprint: str, has_next: bool, next_page_hint: str = "",
                   expected_count: int | None = None) -> dict:
        if not self.validate_creator_center_url(source_url):
            raise PermissionError("扫描检查点只接受抖音创作者中心页面")
        session = self._get(account_id, session_id)
        if session is None:
            raise LookupError(session_id)
        if session["status"] == "cancelled":
            raise ValueError("该扫描已取消")
        repeated_page = session.get("last_page_fingerprint") == page_fingerprint
        old_rows = session.get("scan_rows", [])
        keyed: dict[str, dict] = {}
        anonymous: list[dict] = []
        for row in old_rows:
            key = _record_key(row)
            if key:
                keyed[key] = row
            else:
                anonymous.append(row)
        for row in rows:
            item = {key: value for key, value in row.items() if value is not None}
            key = _record_key(item)
            if not key:
                anonymous.append(item)
                continue
            # When a platform ID appears after an ID-less observation, reconcile it
            # through the same normalized fallback key before inserting a second row.
            fallback = None
            if key.startswith("id:"):
                fallback = _record_key({**item, "platform_post_id": None})
            if fallback and fallback in keyed:
                merged = {**keyed.pop(fallback), **item}
                keyed[key] = merged
            elif key in keyed:
                keyed[key] = {**keyed[key], **item}
            else:
                keyed[key] = item
        merged_rows = [*keyed.values(), *anonymous]
        raw_count = int(session.get("raw_observation_count", 0)) + len(rows)
        duplicate_count = max(0, raw_count - len(merged_rows))
        expected_count = expected_count or session.get("expected_count")
        count_shortfall = bool(not has_next and expected_count and len(merged_rows) < expected_count)
        status = "scanning"
        message = f"已保存第 {int(session.get('pages_scanned', 0)) + 1} 页扫描检查点"
        if session["status"] == "pause_requested":
            status, message = "paused", "当前页已保存，扫描已暂停；可从下一页继续"
        elif session["status"] == "end_requested":
            status, message = "ended", "已保存当前页并按要求结束扫描"
        elif count_shortfall:
            status, message = "paused", f"页面共显示 {expected_count} 条作品，但当前只识别 {len(merged_rows)} 条；检查点已保留，不能确认扫描完成"
            next_page_hint = "请检查筛选条件、未加载内容或页面滚动，再继续扫描"
        elif not has_next:
            status, message = "scan_completed", "已到作品列表末页"
        updated = self._update(account_id, session_id, {
            "status": status,
            "message": "当前页已见作品已按 Session 标识去重，可继续完整扫描。" if repeated_page else message,
            "extension_available": True,
            "source_url": source_url, "scan_rows": merged_rows,
            "raw_observation_count": raw_count, "duplicate_count": duplicate_count,
            "pages_scanned": int(session.get("pages_scanned", 0)) + (0 if repeated_page else 1),
            "last_page_fingerprint": page_fingerprint,
            "next_page_hint": next_page_hint if (has_next or count_shortfall) else None,
            "expected_count": expected_count,
        })
        return self._public(updated)

    def attach_preview(self, account_id: str, session_id: str, preview_id: str, summary: dict,
                       source_url: str) -> dict:
        if not self.validate_creator_center_url(source_url):
            raise PermissionError("只接受从抖音创作者中心页面主动扫描的数据")
        session = self._update(account_id, session_id, {
            "preview_id": preview_id, "summary": summary,
            "status": "scan_completed" if summary.get("snapshot_complete") else "preview_ready",
            "extension_available": True,
            "message": ("扫描完成，预览已送达 Easel；确认前不会写入历史作品"
                        if summary.get("snapshot_complete")
                        else "已生成当前扫描内容的部分预览；补全全量扫描前不能确认对账"),
            "source_url": source_url,
        })
        if session is None:
            raise LookupError(session_id)
        return self.get(account_id, session_id)

    def preview_records(self, account_id: str, session_id: str) -> list[dict]:
        session = self._get(account_id, session_id)
        if session is None:
            raise LookupError(session_id)
        return session.get("scan_rows", [])
