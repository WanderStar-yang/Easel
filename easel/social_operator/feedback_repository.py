"""Persistence for manually recorded publications, weekly reviews, and confirmed memory."""

from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from .repository import AccountNotFoundError, OperatorAccountRepository


class OperatorFeedbackRepository:
    def __init__(self, repository: OperatorAccountRepository | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.repository.initialize()

    @property
    def db_path(self):
        return self.repository.db_path

    def _connect(self) -> sqlite3.Connection:
        return self.repository._connect()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _review(row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "report": json.loads(row["report_json"])}

    @staticmethod
    def _memory(row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "evidence": json.loads(row["evidence_json"])}

    @staticmethod
    def _calendar_event(conn: sqlite3.Connection, *, account_id: str, item_id: str,
                        event_type: str, now: str, actor: str, details: dict[str, Any] | None = None) -> None:
        conn.execute(
            "INSERT INTO operator_content_calendar_events "
            "(id, account_id, calendar_item_id, event_type, occurred_at, actor, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"calendar-event-{uuid4().hex}", account_id, item_id, event_type, now, actor,
             OperatorFeedbackRepository._json(details or {})),
        )

    @staticmethod
    def _calendar_item(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def context(self, account_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            account = conn.execute("SELECT id, name, platform, status FROM operator_accounts WHERE id = ?",
                                   (account_id,)).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            active = conn.execute("SELECT id, version, status FROM operator_active_strategies "
                                  "WHERE account_id = ? AND status = 'ACTIVE'", (account_id,)).fetchone()
            baseline = conn.execute("SELECT id, version, status, sample_size FROM account_baselines "
                                    "WHERE account_id = ? ORDER BY version DESC LIMIT 1", (account_id,)).fetchone()
            topics = []
            if active:
                topics = [dict(row) for row in conn.execute(
                    "SELECT t.id, t.title, t.strategy_id, t.pillar_id, p.name AS pillar_name, "
                    "d.id AS draft_id, d.version AS draft_version "
                    "FROM operator_topics t JOIN operator_content_pillars p "
                    "ON p.id = t.pillar_id AND p.account_id = t.account_id "
                    "LEFT JOIN operator_content_drafts d ON d.topic_id = t.id AND d.status = 'CURRENT' "
                    "WHERE t.account_id = ? AND t.status = 'SELECTED' AND t.strategy_id = ? "
                    "AND p.status = 'ACTIVE' ORDER BY t.created_at DESC", (account_id, active["id"]),
                )]
            posts = [dict(row) for row in conn.execute(
                "SELECT p.id, p.title, p.platform_post_id, p.published_at, p.published_url, p.content_source, "
                "p.hook_type, p.duration_seconds, p.topic_id, t.pillar_id, cp.name AS pillar_name, "
                "(SELECT COUNT(*) FROM operator_post_metrics m WHERE m.published_post_id = p.id) AS checkpoint_count "
                "FROM operator_published_posts p LEFT JOIN operator_topics t ON t.id = p.topic_id "
                "LEFT JOIN operator_content_pillars cp ON cp.id = t.pillar_id "
                "WHERE p.account_id = ? ORDER BY p.published_at DESC LIMIT 100", (account_id,),
            )]
            for post in posts:
                post["metrics"] = [dict(metric) for metric in conn.execute(
                    "SELECT * FROM operator_post_metrics WHERE account_id = ? AND published_post_id = ? "
                    "ORDER BY CASE checkpoint WHEN '24H' THEN 1 WHEN '72H' THEN 2 ELSE 3 END",
                    (account_id, post["id"]),
                )]
            memories = [self._memory(row) for row in conn.execute(
                "SELECT * FROM operator_strategy_memories WHERE account_id = ? AND status = 'ACTIVE' "
                "ORDER BY confirmed_at DESC, id", (account_id,),
            )]
        return {"account": dict(account), "active_strategy": dict(active) if active else None,
                "baseline": dict(baseline) if baseline else None, "selected_topics": topics,
                "published_posts": posts, "active_memories": memories}

    def create_published_post(self, account_id: str, topic_id: str, draft_id: str | None, values: dict,
                             now: str) -> dict[str, Any]:
        post_id = f"published-{uuid4().hex}"
        with self._connect() as conn:
            account = conn.execute("SELECT status, platform FROM operator_accounts WHERE id = ?", (account_id,)).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            if account["status"] != "ACTIVE":
                raise ValueError("只有 ACTIVE 运营账号可以记录发布作品。")
            strategy = conn.execute("SELECT id, version FROM operator_active_strategies "
                                    "WHERE account_id = ? AND status = 'ACTIVE'", (account_id,)).fetchone()
            if strategy is None:
                raise ValueError("账号没有当前 ACTIVE Strategy。")
            topic = conn.execute("SELECT id, title, strategy_id, status FROM operator_topics "
                                 "WHERE id = ? AND account_id = ?", (topic_id, account_id)).fetchone()
            if topic is None or topic["status"] != "SELECTED" or topic["strategy_id"] != strategy["id"]:
                raise ValueError("发布记录必须关联当前账号策略下已选择的选题。")
            existing_post = conn.execute("SELECT id FROM operator_published_posts "
                                          "WHERE account_id = ? AND topic_id = ? LIMIT 1",
                                          (account_id, topic_id)).fetchone()
            if existing_post:
                raise ValueError("该选题已经有实际发布记录，不能重复登记。")
            platform_post_id = str(values.get("platform_post_id") or "").strip() or None
            if platform_post_id and conn.execute(
                "SELECT 1 FROM operator_published_posts WHERE account_id = ? AND platform_post_id = ?",
                (account_id, platform_post_id),
            ).fetchone():
                raise ValueError("该平台作品 ID 已登记，请检查是否重复录入。")
            calendar_plan = conn.execute(
                "SELECT id, status FROM operator_content_calendar WHERE account_id = ? AND topic_id = ? "
                "AND status != 'CANCELLED' ORDER BY created_at DESC LIMIT 1", (account_id, topic_id),
            ).fetchone()
            if calendar_plan and calendar_plan["status"] in {"PUBLISHED", "REVIEWED"}:
                raise ValueError("该选题已通过运营日历登记发布，不能重复登记。")
            if draft_id:
                draft = conn.execute("SELECT id, strategy_id, strategy_version, platform FROM operator_content_drafts "
                                     "WHERE id = ? AND account_id = ? AND topic_id = ? AND status = 'CURRENT'",
                                     (draft_id, account_id, topic_id)).fetchone()
                if draft is None or draft["strategy_id"] != strategy["id"] or draft["platform"] != account["platform"]:
                    raise ValueError("草稿不存在、已过期或与选题/当前策略不匹配。")
            conn.execute(
                "INSERT INTO operator_published_posts "
                "(id, account_id, topic_id, draft_id, strategy_id, strategy_version, platform, platform_post_id, title, "
                "published_url, published_at, content_source, hook_type, duration_seconds, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (post_id, account_id, topic_id, draft_id, strategy["id"], strategy["version"], account["platform"],
                 platform_post_id, values["title"], values.get("published_url"), values["published_at"], values["content_source"],
                 values.get("hook_type"), values.get("duration_seconds"), now, now),
            )
            if calendar_plan:
                conn.execute("UPDATE operator_content_calendar SET status = 'PUBLISHED', actual_publish_at = ?, "
                             "published_url = ?, published_post_id = ?, updated_at = ? "
                             "WHERE id = ? AND account_id = ?",
                             (values["published_at"], values.get("published_url"), post_id, now,
                              calendar_plan["id"], account_id))
                self._calendar_event(conn, account_id=account_id, item_id=calendar_plan["id"],
                                     event_type="PUBLISHED", now=now, actor="local_user",
                                     details={"published_post_id": post_id, "recorded_from": "weekly_review"})
            self._stale_reviews(conn, account_id, now, "新增发布记录")
            row = conn.execute("SELECT p.*, t.title AS topic_title, cp.name AS pillar_name "
                               "FROM operator_published_posts p LEFT JOIN operator_topics t ON t.id = p.topic_id "
                               "LEFT JOIN operator_content_pillars cp ON cp.id = t.pillar_id WHERE p.id = ?",
                               (post_id,)).fetchone()
        return dict(row)

    def create_calendar_item(self, account_id: str, topic_id: str, draft_id: str | None,
                             planned_publish_at: str, now: str) -> dict[str, Any]:
        item_id = f"operator-calendar-{uuid4().hex}"
        try:
            conn_context = self._connect()
            with conn_context as conn:
                account = conn.execute("SELECT status, platform FROM operator_accounts WHERE id = ?",
                                   (account_id,)).fetchone()
                if account is None:
                    raise AccountNotFoundError(account_id)
                if account["status"] != "ACTIVE":
                    raise ValueError("只有 ACTIVE 运营账号可以安排发布计划。")
                strategy = conn.execute("SELECT id, version FROM operator_active_strategies "
                                    "WHERE account_id = ? AND status = 'ACTIVE'", (account_id,)).fetchone()
                if strategy is None:
                    raise ValueError("账号没有当前 ACTIVE Strategy。")
                topic = conn.execute(
                "SELECT t.id, t.title, t.strategy_id FROM operator_topics t "
                "JOIN operator_content_pillars p ON p.id = t.pillar_id AND p.account_id = t.account_id "
                "WHERE t.id = ? AND t.account_id = ? AND t.status = 'SELECTED' AND p.status = 'ACTIVE'",
                (topic_id, account_id),
                ).fetchone()
                if topic is None or topic["strategy_id"] != strategy["id"]:
                    raise ValueError("发布计划必须关联当前策略下已选择的选题。")
                if draft_id:
                    draft = conn.execute("SELECT id, strategy_id, strategy_version, platform FROM operator_content_drafts "
                                     "WHERE id = ? AND account_id = ? AND topic_id = ? AND status = 'CURRENT'",
                                     (draft_id, account_id, topic_id)).fetchone()
                    if (draft is None or draft["strategy_id"] != strategy["id"]
                            or draft["strategy_version"] != strategy["version"]
                            or draft["platform"] != account["platform"]):
                        raise ValueError("只能关联当前策略下该选题的有效草稿。")
                status = "DRAFT" if draft_id else "SELECTED"
                conn.execute(
                "INSERT INTO operator_content_calendar "
                "(id, account_id, topic_id, draft_id, strategy_id, strategy_version, platform, status, "
                "planned_publish_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (item_id, account_id, topic_id, draft_id, strategy["id"], strategy["version"], account["platform"],
                 status, planned_publish_at, now, now),
                )
                self._calendar_event(conn, account_id=account_id, item_id=item_id, event_type="SCHEDULED", now=now,
                                 actor="local_user", details={"planned_publish_at": planned_publish_at,
                                                              "status": status, "topic_id": topic_id})
                row = conn.execute(self._calendar_select() + " WHERE c.id = ? AND c.account_id = ?",
                               (item_id, account_id)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("该选题已有一条有效日历计划；可先调整原计划，或取消后重新安排。") from exc
        return self._calendar_item(row)

    @staticmethod
    def _calendar_select() -> str:
        return ("SELECT c.*, t.title AS topic_title, p.name AS pillar_name, "
                "d.version AS draft_version, pp.title AS published_title "
                "FROM operator_content_calendar c "
                "JOIN operator_topics t ON t.id = c.topic_id AND t.account_id = c.account_id "
                "LEFT JOIN operator_content_pillars p ON p.id = t.pillar_id AND p.account_id = t.account_id "
                "LEFT JOIN operator_content_drafts d ON d.id = c.draft_id AND d.account_id = c.account_id "
                "LEFT JOIN operator_published_posts pp ON pp.id = c.published_post_id AND pp.account_id = c.account_id")

    def list_calendar_items(self, account_id: str, start_at: str, end_at: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM operator_accounts WHERE id = ?", (account_id,)).fetchone() is None:
                raise AccountNotFoundError(account_id)
            rows = conn.execute(self._calendar_select() +
                                " WHERE c.account_id = ? AND c.planned_publish_at >= ? "
                                "AND c.planned_publish_at < ? ORDER BY c.planned_publish_at, c.id",
                                (account_id, start_at, end_at)).fetchall()
            output = []
            for row in rows:
                item = self._calendar_item(row)
                item["events"] = [dict(event) for event in conn.execute(
                    "SELECT event_type, occurred_at, actor, details_json FROM operator_content_calendar_events "
                    "WHERE account_id = ? AND calendar_item_id = ? ORDER BY rowid",
                    (account_id, row["id"]),
                )]
                output.append(item)
        return output

    def update_calendar_date(self, account_id: str, item_id: str, planned_publish_at: str, now: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM operator_content_calendar WHERE id = ? AND account_id = ?",
                               (item_id, account_id)).fetchone()
            if row is None:
                raise ValueError("发布计划不存在或不属于当前账号。")
            if row["status"] not in {"SELECTED", "DRAFT", "READY"}:
                raise ValueError("已发布、已复盘或已取消的记录不能改动计划时间。")
            strategy = conn.execute("SELECT id, version FROM operator_active_strategies "
                                    "WHERE account_id = ? AND status = 'ACTIVE'", (account_id,)).fetchone()
            if strategy is None or strategy["id"] != row["strategy_id"] or strategy["version"] != row["strategy_version"]:
                raise ValueError("该计划绑定的策略已过期，请基于当前策略重新安排。")
            conn.execute("UPDATE operator_content_calendar SET planned_publish_at = ?, updated_at = ? "
                         "WHERE id = ? AND account_id = ?", (planned_publish_at, now, item_id, account_id))
            self._calendar_event(conn, account_id=account_id, item_id=item_id, event_type="RESCHEDULED", now=now,
                                 actor="local_user", details={"from": row["planned_publish_at"],
                                                              "to": planned_publish_at})
            saved = conn.execute(self._calendar_select() + " WHERE c.id = ? AND c.account_id = ?",
                                 (item_id, account_id)).fetchone()
        return self._calendar_item(saved)

    def mark_calendar_ready(self, account_id: str, item_id: str, now: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM operator_content_calendar WHERE id = ? AND account_id = ?",
                               (item_id, account_id)).fetchone()
            if row is None:
                raise ValueError("发布计划不存在或不属于当前账号。")
            if row["status"] not in {"SELECTED", "DRAFT"}:
                raise ValueError("只有选题或草稿状态的计划可以标记为待发布。")
            strategy = conn.execute("SELECT id, version FROM operator_active_strategies "
                                    "WHERE account_id = ? AND status = 'ACTIVE'", (account_id,)).fetchone()
            if strategy is None or strategy["id"] != row["strategy_id"] or strategy["version"] != row["strategy_version"]:
                raise ValueError("该计划绑定的策略已过期，请基于当前策略重新安排。")
            conn.execute("UPDATE operator_content_calendar SET status = 'READY', updated_at = ? "
                         "WHERE id = ? AND account_id = ?", (now, item_id, account_id))
            self._calendar_event(conn, account_id=account_id, item_id=item_id, event_type="READY", now=now,
                                 actor="local_user", details={"from": row["status"], "to": "READY"})
            saved = conn.execute(self._calendar_select() + " WHERE c.id = ? AND c.account_id = ?",
                                 (item_id, account_id)).fetchone()
        return self._calendar_item(saved)

    def cancel_calendar_item(self, account_id: str, item_id: str, now: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM operator_content_calendar WHERE id = ? AND account_id = ?",
                               (item_id, account_id)).fetchone()
            if row is None:
                raise ValueError("发布计划不存在或不属于当前账号。")
            if row["status"] in {"PUBLISHED", "REVIEWED", "CANCELLED"}:
                raise ValueError("已发布、已复盘或已取消的记录不能取消。")
            conn.execute("UPDATE operator_content_calendar SET status = 'CANCELLED', updated_at = ? "
                         "WHERE id = ? AND account_id = ?", (now, item_id, account_id))
            self._calendar_event(conn, account_id=account_id, item_id=item_id, event_type="CANCELLED", now=now,
                                 actor="local_user", details={"from": row["status"]})
            saved = conn.execute(self._calendar_select() + " WHERE c.id = ? AND c.account_id = ?",
                                 (item_id, account_id)).fetchone()
        return self._calendar_item(saved)

    def publish_calendar_item(self, account_id: str, item_id: str, values: dict[str, Any], now: str) -> dict[str, Any]:
        post_id = f"published-{uuid4().hex}"
        with self._connect() as conn:
            plan = conn.execute("SELECT * FROM operator_content_calendar WHERE id = ? AND account_id = ?",
                                (item_id, account_id)).fetchone()
            if plan is None:
                raise ValueError("发布计划不存在或不属于当前账号。")
            if plan["status"] != "READY":
                raise ValueError("只有标记为待发布的计划可以登记实际发布。")
            account = conn.execute("SELECT status, platform FROM operator_accounts WHERE id = ?",
                                   (account_id,)).fetchone()
            strategy = conn.execute("SELECT id, version FROM operator_active_strategies "
                                    "WHERE account_id = ? AND status = 'ACTIVE'", (account_id,)).fetchone()
            if (account is None or account["status"] != "ACTIVE" or strategy is None
                    or strategy["id"] != plan["strategy_id"] or strategy["version"] != plan["strategy_version"]):
                raise ValueError("账号或计划策略已失效，请按当前 ACTIVE Strategy 重新安排。")
            existing_post = conn.execute("SELECT id FROM operator_published_posts "
                                          "WHERE account_id = ? AND topic_id = ? LIMIT 1",
                                          (account_id, plan["topic_id"])).fetchone()
            if existing_post:
                raise ValueError("该选题已经有实际发布记录，不能重复登记。")
            platform_post_id = str(values.get("platform_post_id") or "").strip() or None
            if platform_post_id and conn.execute(
                "SELECT 1 FROM operator_published_posts WHERE account_id = ? AND platform_post_id = ?",
                (account_id, platform_post_id),
            ).fetchone():
                raise ValueError("该平台作品 ID 已登记，请检查是否重复录入。")
            if values.get("title") is None or not str(values["title"]).strip():
                raise ValueError("实际发布标题不能为空。")
            conn.execute(
                "INSERT INTO operator_published_posts "
                "(id, account_id, topic_id, draft_id, strategy_id, strategy_version, platform, platform_post_id, title, "
                "published_url, published_at, content_source, hook_type, duration_seconds, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (post_id, account_id, plan["topic_id"], plan["draft_id"], plan["strategy_id"],
                 plan["strategy_version"], plan["platform"], platform_post_id, str(values["title"]).strip(),
                 values.get("published_url"), values["published_at"], values["content_source"],
                 values.get("hook_type"), values.get("duration_seconds"), now, now),
            )
            conn.execute("UPDATE operator_content_calendar SET status = 'PUBLISHED', actual_publish_at = ?, "
                         "published_url = ?, published_post_id = ?, updated_at = ? WHERE id = ? AND account_id = ?",
                         (values["published_at"], values.get("published_url"), post_id, now, item_id, account_id))
            self._calendar_event(conn, account_id=account_id, item_id=item_id, event_type="PUBLISHED", now=now,
                                 actor="local_user", details={"published_post_id": post_id,
                                                              "actual_publish_at": values["published_at"]})
            self._stale_reviews(conn, account_id, now, "新增发布记录")
            saved = conn.execute(self._calendar_select() + " WHERE c.id = ? AND c.account_id = ?",
                                 (item_id, account_id)).fetchone()
        return self._calendar_item(saved)

    @staticmethod
    def _stale_reviews(conn: sqlite3.Connection, account_id: str, now: str, reason: str) -> None:
        review_ids = [row["id"] for row in conn.execute(
            "SELECT id FROM operator_weekly_reviews WHERE account_id = ? AND status = 'CURRENT'", (account_id,)
        )]
        if not review_ids:
            return
        conn.execute("UPDATE operator_weekly_reviews SET status = 'STALE' WHERE account_id = ? AND status = 'CURRENT'",
                     (account_id,))
        placeholders = ",".join("?" for _ in review_ids)
        reviewed_plans = conn.execute(
            "SELECT id, review_id FROM operator_content_calendar WHERE account_id = ? "
            f"AND status = 'REVIEWED' AND review_id IN ({placeholders})", (account_id, *review_ids),
        ).fetchall()
        for plan in reviewed_plans:
            conn.execute("UPDATE operator_content_calendar SET status = 'PUBLISHED', review_id = NULL, updated_at = ? "
                         "WHERE account_id = ? AND id = ?", (now, account_id, plan["id"]))
            OperatorFeedbackRepository._calendar_event(
                conn, account_id=account_id, item_id=plan["id"], event_type="REVIEW_INVALIDATED", now=now,
                actor="system", details={"review_id": plan["review_id"], "reason": reason},
            )
        for review_id in review_ids:
            active_memories = conn.execute(
                "SELECT * FROM operator_strategy_memories WHERE account_id = ? AND review_id = ? "
                "AND status IN ('ACTIVE', 'PROPOSED')",
                (account_id, review_id),
            ).fetchall()
            for memory in active_memories:
                conn.execute("UPDATE operator_strategy_memories SET status = 'STALE' WHERE id = ?", (memory["id"],))
                conn.execute("INSERT INTO operator_strategy_memory_events "
                             "(id, account_id, memory_id, review_id, event_type, occurred_at, actor, details_json) "
                             "VALUES (?, ?, ?, ?, 'STALE', ?, 'system', ?)",
                             (f"memory-event-{uuid4().hex}", account_id, memory["id"], review_id, now,
                              OperatorFeedbackRepository._json({"reason": reason})))

    def list_posts(self, account_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM operator_accounts WHERE id = ?", (account_id,)).fetchone() is None:
                raise AccountNotFoundError(account_id)
            rows = conn.execute(
                "SELECT p.*, t.title AS topic_title, cp.name AS pillar_name "
                "FROM operator_published_posts p LEFT JOIN operator_topics t ON t.id = p.topic_id "
                "LEFT JOIN operator_content_pillars cp ON cp.id = t.pillar_id "
                "WHERE p.account_id = ? ORDER BY p.published_at DESC", (account_id,),
            ).fetchall()
            output = []
            for row in rows:
                item = dict(row)
                item["metrics"] = [dict(m) for m in conn.execute(
                    "SELECT * FROM operator_post_metrics WHERE account_id = ? AND published_post_id = ? "
                    "ORDER BY CASE checkpoint WHEN '24H' THEN 1 WHEN '72H' THEN 2 ELSE 3 END",
                    (account_id, row["id"]),
                )]
                output.append(item)
        return output

    def save_metric(self, account_id: str, post_id: str, checkpoint: str, values: dict[str, Any], now: str) -> dict[str, Any]:
        metric_id = f"metric-{uuid4().hex}"
        columns = ("views", "likes", "comments", "favorites", "shares", "followers_gain", "profile_visits", "inquiries")
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM operator_published_posts WHERE id = ? AND account_id = ?",
                            (post_id, account_id)).fetchone() is None:
                raise ValueError("发布作品不存在或不属于当前账号。")
            conn.execute(
                "INSERT INTO operator_post_metrics (id, account_id, published_post_id, checkpoint, "
                + ", ".join(columns) + ", recorded_at) VALUES ("
                + ", ".join("?" for _ in range(4 + len(columns) + 1)) + ") "
                "ON CONFLICT(published_post_id, checkpoint) DO UPDATE SET "
                + ", ".join(f"{column}=excluded.{column}" for column in columns)
                + ", recorded_at=excluded.recorded_at",
                (metric_id, account_id, post_id, checkpoint, *(values.get(column) for column in columns), now),
            )
            self._stale_reviews(conn, account_id, now, "发布指标已更新")
            row = conn.execute("SELECT * FROM operator_post_metrics WHERE account_id = ? AND published_post_id = ? "
                               "AND checkpoint = ?", (account_id, post_id, checkpoint)).fetchone()
        return dict(row)

    def posts_for_week(self, account_id: str, week_start: str, week_end_exclusive: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM operator_accounts WHERE id = ?", (account_id,)).fetchone() is None:
                raise AccountNotFoundError(account_id)
            rows = conn.execute(
                "SELECT p.*, t.title AS topic_title, t.pillar_id, cp.name AS pillar_name "
                "FROM operator_published_posts p LEFT JOIN operator_topics t ON t.id = p.topic_id "
                "LEFT JOIN operator_content_pillars cp ON cp.id = t.pillar_id "
                "WHERE p.account_id = ? AND p.published_at >= ? AND p.published_at < ? ORDER BY p.published_at, p.id",
                (account_id, week_start, week_end_exclusive),
            ).fetchall()
            output = []
            for row in rows:
                item = dict(row)
                item["metrics"] = [dict(m) for m in conn.execute(
                    "SELECT * FROM operator_post_metrics WHERE account_id = ? AND published_post_id = ? "
                    "ORDER BY CASE checkpoint WHEN '24H' THEN 1 WHEN '72H' THEN 2 ELSE 3 END",
                    (account_id, row["id"]),
                )]
                output.append(item)
        return output

    def save_review(self, account_id: str, week_start: str, week_end: str, baseline_id: str | None,
                    baseline_version: int | None, source_version: str, report: dict[str, Any], now: str) -> dict[str, Any]:
        review_id = f"weekly-review-{uuid4().hex}"
        with self._connect() as conn:
            current = conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM operator_weekly_reviews "
                                   "WHERE account_id = ? AND week_start = ?", (account_id, week_start)).fetchone()
            version = int(current["version"]) + 1
            conn.execute("UPDATE operator_weekly_reviews SET status = 'SUPERSEDED' "
                         "WHERE account_id = ? AND week_start = ? AND status = 'CURRENT'", (account_id, week_start))
            conn.execute(
                "INSERT INTO operator_weekly_reviews "
                "(id, account_id, version, week_start, week_end, baseline_id, baseline_version, "
                "source_data_version, status, generated_at, report_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CURRENT', ?, ?)",
                (review_id, account_id, version, week_start, week_end, baseline_id, baseline_version,
                 source_version, now, self._json(report)),
            )
            for candidate in report.get("memory_candidates", []):
                memory_key = candidate["memory_key"]
                latest = conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM operator_strategy_memories "
                                      "WHERE account_id = ? AND memory_key = ?", (account_id, memory_key)).fetchone()
                conn.execute(
                    "INSERT INTO operator_strategy_memories "
                    "(id, account_id, review_id, memory_key, version, status, statement, evidence_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 'PROPOSED', ?, ?, ?)",
                    (candidate["id"], account_id, review_id, memory_key, int(latest["version"]) + 1,
                     candidate["statement"], self._json(candidate["evidence"]), now),
                )
            published_ids = [item.get("published_post_id") for item in report.get("posts", [])
                             if item.get("published_post_id")]
            if published_ids:
                placeholders = ",".join("?" for _ in published_ids)
                plans = conn.execute(
                    "SELECT id, status FROM operator_content_calendar WHERE account_id = ? "
                    f"AND published_post_id IN ({placeholders})", (account_id, *published_ids),
                ).fetchall()
                for plan in plans:
                    conn.execute("UPDATE operator_content_calendar SET status = 'REVIEWED', review_id = ?, updated_at = ? "
                                 "WHERE account_id = ? AND id = ?",
                                 (review_id, now, account_id, plan["id"]))
                    self._calendar_event(conn, account_id=account_id, item_id=plan["id"], event_type="REVIEWED",
                                         now=now, actor="system", details={"review_id": review_id,
                                                                             "previous_status": plan["status"]})
            row = conn.execute("SELECT * FROM operator_weekly_reviews WHERE id = ?", (review_id,)).fetchone()
        return self._review(row)

    def get_review(self, account_id: str, review_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM operator_weekly_reviews WHERE id = ? AND account_id = ?",
                               (review_id, account_id)).fetchone()
            if row is None:
                return None
            result = self._review(row)
            result["memories"] = [self._memory(item) for item in conn.execute(
                "SELECT * FROM operator_strategy_memories WHERE review_id = ? AND account_id = ? ORDER BY created_at, id",
                (review_id, account_id),
            )]
        return result

    def list_reviews(self, account_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM operator_accounts WHERE id = ?", (account_id,)).fetchone() is None:
                raise AccountNotFoundError(account_id)
            rows = conn.execute("SELECT * FROM operator_weekly_reviews WHERE account_id = ? "
                                "ORDER BY week_start DESC, version DESC LIMIT ?", (account_id, limit)).fetchall()
        return [self._review(row) for row in rows]

    def decide_memory(self, account_id: str, memory_id: str, *, confirm: bool, statement: str,
                      actor: str, now: str) -> dict[str, Any]:
        event_id = f"memory-event-{uuid4().hex}"
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM operator_strategy_memories WHERE id = ? AND account_id = ?",
                               (memory_id, account_id)).fetchone()
            if row is None:
                raise ValueError("Strategy Memory 不存在或不属于当前账号。")
            if row["status"] != "PROPOSED":
                raise ValueError("只有待审核 Memory 可以确认或忽略。")
            review = conn.execute("SELECT status FROM operator_weekly_reviews WHERE id = ? AND account_id = ?",
                                  (row["review_id"], account_id)).fetchone()
            if review is None or review["status"] != "CURRENT":
                raise ValueError("来源 Weekly Review 已过期，请先重新生成复盘。")
            if confirm:
                previous = conn.execute("SELECT * FROM operator_strategy_memories WHERE account_id = ? "
                                        "AND memory_key = ? AND status = 'ACTIVE'",
                                        (account_id, row["memory_key"])).fetchall()
                for old in previous:
                    conn.execute("UPDATE operator_strategy_memories SET status = 'SUPERSEDED' WHERE id = ?",
                                 (old["id"],))
                    conn.execute("INSERT INTO operator_strategy_memory_events "
                                 "(id, account_id, memory_id, review_id, event_type, occurred_at, actor, details_json) "
                                 "VALUES (?, ?, ?, ?, 'SUPERSEDED', ?, 'system', ?)",
                                 (f"memory-event-{uuid4().hex}", account_id, old["id"], old["review_id"], now,
                                  self._json({"replaced_by": memory_id})))
                conn.execute("UPDATE operator_strategy_memories SET status = 'ACTIVE', statement = ?, "
                             "confirmed_at = ?, confirmed_by = ? WHERE id = ? AND account_id = ?",
                             (statement, now, actor, memory_id, account_id))
                event_type = "CONFIRMED"
            else:
                conn.execute("UPDATE operator_strategy_memories SET status = 'DISMISSED' "
                             "WHERE id = ? AND account_id = ?", (memory_id, account_id))
                event_type = "DISMISSED"
            conn.execute("INSERT INTO operator_strategy_memory_events "
                         "(id, account_id, memory_id, review_id, event_type, occurred_at, actor, details_json) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (event_id, account_id, memory_id, row["review_id"], event_type, now, actor,
                          self._json({"statement": statement if confirm else row["statement"]})))
            saved = conn.execute("SELECT * FROM operator_strategy_memories WHERE id = ?", (memory_id,)).fetchone()
        return self._memory(saved)

    def list_memories(self, account_id: str, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM operator_accounts WHERE id = ?", (account_id,)).fetchone() is None:
                raise AccountNotFoundError(account_id)
            if status:
                rows = conn.execute("SELECT * FROM operator_strategy_memories WHERE account_id = ? AND status = ? "
                                    "ORDER BY created_at DESC, id", (account_id, status)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM operator_strategy_memories WHERE account_id = ? "
                                    "ORDER BY created_at DESC, id", (account_id,)).fetchall()
        return [self._memory(row) for row in rows]

    def list_active_strategy_memories(self, account_id: str) -> list[dict[str, Any]]:
        return self.list_memories(account_id, "ACTIVE")
