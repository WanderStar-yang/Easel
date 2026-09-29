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
                PRAGMA user_version = 1;
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
