"""SQLite persistence for isolated Social Operator V1 business data."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "outputs" / "_social_operator.sqlite3"


class AccountNotFoundError(LookupError):
    pass


class DuplicatePlatformError(ValueError):
    pass


class OperatorAccountRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        configured = db_path or os.environ.get("EASEL_SOCIAL_OPERATOR_DB_PATH")
        self.db_path = Path(configured) if configured else DEFAULT_DB_PATH

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS operator_accounts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    platform TEXT NOT NULL UNIQUE CHECK (platform IN ('douyin', 'xiaohongshu')),
                    status TEXT NOT NULL CHECK (status IN (
                        'NEW', 'IMPORTING', 'DIAGNOSING',
                        'STRATEGY_PENDING_CONFIRMATION', 'ACTIVE', 'REVIEWING'
                    )),
                    diagnosis_completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operator_profiles (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL UNIQUE REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    summary TEXT NOT NULL DEFAULT '',
                    easel_profile_name TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS operator_strategies (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL UNIQUE REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    summary TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'hypothesis'
                        CHECK (state IN ('hypothesis', 'recommended', 'confirmed')),
                    confirmed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS historical_posts (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    platform TEXT NOT NULL CHECK (platform IN ('douyin', 'xiaohongshu')),
                    publish_time TEXT,
                    title TEXT NOT NULL,
                    content_type TEXT,
                    content_source TEXT NOT NULL CHECK (content_source IN ('REAL', 'AI', 'MIXED', 'UNKNOWN')),
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    note TEXT,
                    duration REAL CHECK (duration IS NULL OR duration >= 0),
                    subjects_json TEXT NOT NULL DEFAULT '[]',
                    hook_type TEXT,
                    views INTEGER CHECK (views IS NULL OR views >= 0),
                    likes INTEGER CHECK (likes IS NULL OR likes >= 0),
                    comments INTEGER CHECK (comments IS NULL OR comments >= 0),
                    favorites INTEGER CHECK (favorites IS NULL OR favorites >= 0),
                    shares INTEGER CHECK (shares IS NULL OR shares >= 0),
                    followers_gain INTEGER,
                    profile_visits INTEGER CHECK (profile_visits IS NULL OR profile_visits >= 0),
                    inquiries INTEGER CHECK (inquiries IS NULL OR inquiries >= 0),
                    platform_post_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_historical_posts_account_time
                    ON historical_posts(account_id, publish_time DESC, id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_historical_posts_platform_id
                    ON historical_posts(account_id, platform_post_id)
                    WHERE platform_post_id IS NOT NULL AND platform_post_id != '';
                PRAGMA user_version = 2;
                """
            )

    def seed_defaults(self, now: str) -> None:
        seeds = (
            (
                "douyin-pet", "抖音宠物账号", "douyin",
                "缅因猫与布偶猫的双猫家庭内容方向（初始假设）",
                "宠物双猫家庭（初始假设；待历史数据诊断和用户确认）",
            ),
            (
                "xhs-developer", "小红书独立开发者账号", "xiaohongshu",
                "独立开发、真实项目与 AI Coding（初始假设）",
                "独立开发者真实项目记录（初始假设；待历史数据诊断和用户确认）",
            ),
        )
        with self._connect() as conn:
            for account_id, name, platform, profile_summary, strategy_summary in seeds:
                conn.execute(
                    "INSERT OR IGNORE INTO operator_accounts "
                    "(id, name, platform, status, created_at, updated_at) VALUES (?, ?, ?, 'NEW', ?, ?)",
                    (account_id, name, platform, now, now),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO operator_profiles (id, account_id, summary) VALUES (?, ?, ?)",
                    (f"profile-{account_id}", account_id, profile_summary),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO operator_strategies (id, account_id, summary) VALUES (?, ?, ?)",
                    (f"strategy-{account_id}", account_id, strategy_summary),
                )

    @staticmethod
    def _account(row: sqlite3.Row) -> dict[str, Any]:
        profile, strategy = row["profile"], row["strategy"]
        return {
            "id": row["id"], "name": row["name"], "platform": row["platform"],
            "status": row["status"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "diagnosis_completed_at": row["diagnosis_completed_at"],
            "profile": json.loads(profile) if profile else None,
            "strategy": json.loads(strategy) if strategy else None,
        }

    def _select(self, conn: sqlite3.Connection, account_id: str | None = None):
        where = "WHERE a.id = ?" if account_id else ""
        params = (account_id,) if account_id else ()
        return conn.execute(
            f"""SELECT a.*,
                (SELECT json_object('id', p.id, 'account_id', p.account_id, 'summary', p.summary,
                    'easel_profile_name', p.easel_profile_name, 'details_json', p.details_json)
                    FROM operator_profiles p WHERE p.account_id = a.id) AS profile,
                (SELECT json_object('id', s.id, 'account_id', s.account_id, 'summary', s.summary,
                    'state', s.state, 'confirmed_at', s.confirmed_at)
                    FROM operator_strategies s WHERE s.account_id = a.id) AS strategy
                FROM operator_accounts a {where} ORDER BY a.created_at, a.id""",
            params,
        )

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [self._account(row) for row in self._select(conn).fetchall()]

    def get_account(self, account_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = self._select(conn, account_id).fetchone()
        if row is None:
            raise AccountNotFoundError(account_id)
        return self._account(row)

    def create_account(self, *, account_id: str, name: str, platform: str,
                       profile_summary: str, strategy_summary: str, now: str) -> dict[str, Any]:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO operator_accounts (id, name, platform, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'NEW', ?, ?)", (account_id, name, platform, now, now),
                )
                conn.execute(
                    "INSERT INTO operator_profiles (id, account_id, summary) VALUES (?, ?, ?)",
                    (f"profile-{account_id}", account_id, profile_summary),
                )
                conn.execute(
                    "INSERT INTO operator_strategies (id, account_id, summary) VALUES (?, ?, ?)",
                    (f"strategy-{account_id}", account_id, strategy_summary),
                )
        except sqlite3.IntegrityError as exc:
            if "platform" in str(exc).lower():
                raise DuplicatePlatformError(platform) from exc
            raise
        return self.get_account(account_id)

    def update_account(self, account_id: str, values: dict[str, Any], now: str) -> dict[str, Any]:
        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM operator_accounts WHERE id = ?", (account_id,)).fetchone()
            if exists is None:
                raise AccountNotFoundError(account_id)
            if "name" in values:
                conn.execute("UPDATE operator_accounts SET name = ?, updated_at = ? WHERE id = ?",
                             (values["name"], now, account_id))
            if "status" in values:
                conn.execute("UPDATE operator_accounts SET status = ?, updated_at = ? WHERE id = ?",
                             (values["status"], now, account_id))
            if "profile_summary" in values:
                conn.execute("UPDATE operator_profiles SET summary = ? WHERE account_id = ?",
                             (values["profile_summary"], account_id))
            if "easel_profile_name" in values:
                conn.execute("UPDATE operator_profiles SET easel_profile_name = ? WHERE account_id = ?",
                             (values["easel_profile_name"], account_id))
            if "strategy_summary" in values:
                conn.execute("UPDATE operator_strategies SET summary = ? WHERE account_id = ?",
                             (values["strategy_summary"], account_id))
        return self.get_account(account_id)

    @staticmethod
    def _post(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["tags"] = json.loads(result.pop("tags_json"))
        result["subjects"] = json.loads(result.pop("subjects_json"))
        return result

    def list_posts(self, account_id: str, *, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM historical_posts WHERE account_id = ? "
                "ORDER BY publish_time IS NULL, publish_time DESC, created_at DESC LIMIT ? OFFSET ?",
                (account_id, limit, offset),
            ).fetchall()
        return [self._post(row) for row in rows]

    def count_posts(self, account_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM historical_posts WHERE account_id = ?",
                               (account_id,)).fetchone()
        return int(row["total"])

    def get_post(self, account_id: str, post_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_posts WHERE account_id = ? AND id = ?",
                (account_id, post_id),
            ).fetchone()
        return self._post(row) if row else None

    @staticmethod
    def _duplicate_query(conn: sqlite3.Connection, values: dict[str, Any], exclude_id: str | None = None):
        if values.get("platform_post_id"):
            sql = "SELECT id FROM historical_posts WHERE account_id = ? AND platform_post_id = ?"
            params: tuple[Any, ...] = (values["account_id"], values["platform_post_id"])
        elif values.get("publish_time") and values.get("title"):
            sql = "SELECT id FROM historical_posts WHERE account_id = ? AND platform = ? " \
                  "AND publish_time = ? AND lower(trim(title)) = lower(trim(?))"
            params = (values["account_id"], values["platform"], values["publish_time"], values["title"])
        else:
            return None
        if exclude_id:
            sql += " AND id != ?"
            params += (exclude_id,)
        row = conn.execute(sql + " LIMIT 1", params).fetchone()
        return row["id"] if row else None

    def find_duplicate(self, values: dict[str, Any], exclude_id: str | None = None) -> str | None:
        with self._connect() as conn:
            return self._duplicate_query(conn, values, exclude_id)

    def create_post(self, post_id: str, values: dict[str, Any], now: str) -> dict[str, Any]:
        inserted, duplicates = self.create_posts([(post_id, values)], now)
        if duplicates:
            return {"duplicate_id": duplicates[0][1]}
        return self.get_post(values["account_id"], inserted[0]) or {}

    def create_posts(self, posts: list[tuple[str, dict[str, Any]]], now: str) -> tuple[list[str], list[tuple[str, str]]]:
        columns = (
            "account_id", "platform", "publish_time", "title", "content_type", "content_source",
            "tags_json", "note", "duration", "subjects_json", "hook_type", "views", "likes",
            "comments", "favorites", "shares", "followers_gain", "profile_visits", "inquiries",
            "platform_post_id",
        )
        inserted: list[str] = []
        duplicates: list[tuple[str, str]] = []
        with self._connect() as conn:
            for post_id, values in posts:
                duplicate_id = self._duplicate_query(conn, values)
                if duplicate_id:
                    duplicates.append((post_id, duplicate_id))
                    continue
                stored = dict(values)
                stored["tags_json"] = json.dumps(stored.pop("tags", []), ensure_ascii=False)
                stored["subjects_json"] = json.dumps(stored.pop("subjects", []), ensure_ascii=False)
                conn.execute(
                    f"INSERT INTO historical_posts (id, {', '.join(columns)}, created_at, updated_at) "
                    f"VALUES ({', '.join('?' for _ in range(len(columns) + 3))})",
                    (post_id, *(stored.get(column) for column in columns), now, now),
                )
                inserted.append(post_id)
        return inserted, duplicates

    def update_post(self, account_id: str, post_id: str, values: dict[str, Any], now: str) -> dict[str, Any] | None:
        current = self.get_post(account_id, post_id)
        if current is None:
            return None
        merged = {**current, **values, "account_id": account_id}
        with self._connect() as conn:
            duplicate_id = self._duplicate_query(conn, merged, exclude_id=post_id)
            if duplicate_id:
                return {"duplicate_id": duplicate_id}
            assignments: list[str] = []
            params: list[Any] = []
            for key, value in values.items():
                column = {"tags": "tags_json", "subjects": "subjects_json"}.get(key, key)
                if key in {"tags", "subjects"}:
                    value = json.dumps(value, ensure_ascii=False)
                assignments.append(f"{column} = ?")
                params.append(value)
            assignments.append("updated_at = ?")
            params.extend((now, account_id, post_id))
            conn.execute(
                f"UPDATE historical_posts SET {', '.join(assignments)} WHERE account_id = ? AND id = ?",
                params,
            )
        return self.get_post(account_id, post_id)

    def delete_post(self, account_id: str, post_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM historical_posts WHERE account_id = ? AND id = ?", (account_id, post_id)
            )
            return cursor.rowcount > 0
