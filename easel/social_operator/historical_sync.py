"""Short-lived, account-bound sessions for explicitly initiated local browser sync."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from urllib.parse import urlparse

SESSION_TTL = timedelta(minutes=15)


class HistoricalSyncSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def create(self, account_id: str) -> dict:
        now = self._now()
        session_id = token_urlsafe(32)
        session = {"account_id": account_id, "created_at": now, "expires_at": now + SESSION_TTL,
                   "preview_id": None, "summary": None}
        with self._lock:
            self._prune(now)
            self._sessions[session_id] = session
        return {"session_id": session_id, "expires_at": session["expires_at"].isoformat(),
                "status": "waiting_for_scan"}

    def _prune(self, now: datetime) -> None:
        expired = [key for key, value in self._sessions.items() if value["expires_at"] <= now]
        for key in expired:
            self._sessions.pop(key, None)

    @staticmethod
    def validate_creator_center_url(source_url: str) -> bool:
        parsed = urlparse(source_url)
        return parsed.scheme == "https" and parsed.hostname == "creator.douyin.com"

    def attach_preview(self, account_id: str, session_id: str, preview_id: str, summary: dict,
                       source_url: str) -> dict:
        if not self.validate_creator_center_url(source_url):
            raise PermissionError("只接受从抖音创作者中心页面主动扫描的数据")
        with self._lock:
            self._prune(self._now())
            session = self._sessions.get(session_id)
            if session is None or session["account_id"] != account_id:
                raise LookupError(session_id)
            session["preview_id"] = preview_id
            session["summary"] = summary
        return self.get(account_id, session_id)

    def get(self, account_id: str, session_id: str) -> dict:
        with self._lock:
            self._prune(self._now())
            session = self._sessions.get(session_id)
            if session is None or session["account_id"] != account_id:
                raise LookupError(session_id)
            return {
                "session_id": session_id,
                "status": "preview_ready" if session["preview_id"] else "waiting_for_scan",
                "preview_id": session["preview_id"],
                "preview": session["summary"],
                "expires_at": session["expires_at"].isoformat(),
            }
