"""Account-scoped planning for selected Social Operator Topics."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .feedback_repository import OperatorFeedbackRepository
from .repository import AccountNotFoundError, OperatorAccountRepository

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")


class OperatorContentCalendarService:
    def __init__(self, repository: OperatorAccountRepository | None = None, *,
                 feedback: OperatorFeedbackRepository | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.repository.initialize()
        self.feedback = feedback or OperatorFeedbackRepository(self.repository)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(LOCAL_TIMEZONE)

    @staticmethod
    def _timestamp(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("时间格式无效，请使用 ISO 日期时间。") from exc
        if parsed.tzinfo is None:
            raise ValueError("时间必须包含时区信息。")
        return parsed.astimezone(LOCAL_TIMEZONE).isoformat(timespec="seconds")

    def context(self, account_id: str, start_date: str, end_date: str) -> dict[str, Any]:
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError as exc:
            raise ValueError("请选择有效的日历日期范围。") from exc
        if end < start:
            raise ValueError("日历结束日期不能早于开始日期。")
        if (end - start).days > 92:
            raise ValueError("单次最多查看 93 天。")
        context = self.feedback.context(account_id)
        start_at = datetime.combine(start, time.min, LOCAL_TIMEZONE).isoformat(timespec="seconds")
        end_at = datetime.combine(date.fromordinal(end.toordinal() + 1), time.min,
                                  LOCAL_TIMEZONE).isoformat(timespec="seconds")
        items = self.feedback.list_calendar_items(account_id, start_at, end_at)
        active = context.get("active_strategy")
        for item in items:
            item["strategy_is_current"] = bool(active and active.get("id") == item["strategy_id"]
                                               and active.get("version") == item["strategy_version"])
        context["calendar_items"] = items
        return context

    def schedule(self, account_id: str, topic_id: str, draft_id: str | None,
                 planned_publish_at: str) -> dict[str, Any]:
        planned = self._timestamp(planned_publish_at)
        now = self._now().isoformat(timespec="seconds")
        return self.feedback.create_calendar_item(account_id, topic_id, draft_id, planned, now)

    def reschedule(self, account_id: str, item_id: str, planned_publish_at: str) -> dict[str, Any]:
        planned = self._timestamp(planned_publish_at)
        return self.feedback.update_calendar_date(account_id, item_id, planned,
                                                  self._now().isoformat(timespec="seconds"))

    def mark_ready(self, account_id: str, item_id: str) -> dict[str, Any]:
        return self.feedback.mark_calendar_ready(account_id, item_id,
                                                 self._now().isoformat(timespec="seconds"))

    def cancel(self, account_id: str, item_id: str) -> dict[str, Any]:
        return self.feedback.cancel_calendar_item(account_id, item_id,
                                                  self._now().isoformat(timespec="seconds"))

    def mark_published(self, account_id: str, item_id: str, values: dict[str, Any]) -> dict[str, Any]:
        title = str(values.get("title") or "").strip()
        if not title or len(title) > 200:
            raise ValueError("实际发布标题为必填项，最多 200 个字。")
        if values.get("content_source") not in {"REAL", "AI", "MIXED", "UNKNOWN"}:
            raise ValueError("内容来源必须是 REAL、AI、MIXED 或 UNKNOWN。")
        if values.get("duration_seconds") is not None:
            try:
                duration = int(values["duration_seconds"])
            except (TypeError, ValueError) as exc:
                raise ValueError("作品时长必须是正整数。") from exc
            if duration <= 0:
                raise ValueError("作品时长必须大于 0 秒。")
            values = {**values, "duration_seconds": duration}
        normalized = {**values, "title": title,
                      "platform_post_id": str(values.get("platform_post_id") or "").strip() or None,
                      "published_at": self._timestamp(values.get("published_at"))}
        return self.feedback.publish_calendar_item(account_id, item_id, normalized,
                                                   self._now().isoformat(timespec="seconds"))
