"""SQLite persistence for isolated Social Operator V1 business data."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from .canonical import clean_title

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "outputs" / "_social_operator.sqlite3"


def datetime_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_legacy_scan_title(value: str) -> str:
    return clean_title(value)


def _remap_report_references(report: dict[str, Any], id_map: dict[str, str]) -> dict[str, Any]:
    list_reference_keys = {"historical_post_ids", "evidence_post_ids_a", "evidence_post_ids_b"}

    def visit(value: Any, key: str | None = None) -> Any:
        if isinstance(value, list):
            items = [visit(item, key) for item in value]
            if key in list_reference_keys:
                return list(dict.fromkeys(id_map.get(str(item), str(item)) for item in items))
            if key in {"historical_post_versions", "top_posts", "low_posts"}:
                deduped: list[Any] = []
                seen: set[str] = set()
                for item in items:
                    item_id = str(item.get("id")) if isinstance(item, dict) and item.get("id") else None
                    if item_id and item_id in seen:
                        continue
                    if item_id:
                        seen.add(item_id)
                    deduped.append(item)
                return deduped
            return items
        if isinstance(value, dict):
            result = {child_key: visit(child, child_key) for child_key, child in value.items()}
            if result.get("id") is not None and key in {"historical_post_versions", "top_posts", "low_posts"}:
                result["id"] = id_map.get(str(result["id"]), str(result["id"]))
            return result
        return value

    return visit(report)


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
                    last_sync_at TEXT,
                    last_sync_source TEXT,
                    last_sync_counts_json TEXT NOT NULL DEFAULT '{}',
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
                    publish_time_raw TEXT,
                    title TEXT NOT NULL,
                    content_type TEXT,
                    content_type_raw TEXT,
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
                    data_source TEXT NOT NULL DEFAULT 'MANUAL',
                    source_updated_at TEXT,
                    source_presence TEXT NOT NULL DEFAULT 'PRESENT' CHECK (source_presence IN ('PRESENT', 'MISSING')),
                    missing_since TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_historical_posts_account_time
                    ON historical_posts(account_id, publish_time DESC, id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_historical_posts_platform_id
                    ON historical_posts(account_id, platform_post_id)
                    WHERE platform_post_id IS NOT NULL AND platform_post_id != '';
                CREATE TABLE IF NOT EXISTS account_diagnoses (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    algorithm_version TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'CURRENT' CHECK (status IN ('CURRENT', 'STALE')),
                    stale_at TEXT,
                    stale_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS account_baselines (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    sample_size INTEGER NOT NULL CHECK (sample_size >= 0),
                    period_start TEXT,
                    period_end TEXT,
                    generated_at TEXT NOT NULL,
                    source_updated_at TEXT,
                    historical_data_version TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'STALE')),
                    report_json TEXT NOT NULL,
                    UNIQUE(account_id, version)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_account_baselines_one_active
                    ON account_baselines(account_id) WHERE status = 'ACTIVE';
                CREATE INDEX IF NOT EXISTS idx_account_baselines_history
                    ON account_baselines(account_id, version DESC);
                CREATE TABLE IF NOT EXISTS historical_post_archive (
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    post_id TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    archived_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, post_id)
                );
                CREATE INDEX IF NOT EXISTS idx_account_diagnoses_latest
                    ON account_diagnoses(account_id, generated_at DESC, id DESC);
                """
            )
            # Additive migration: preserve databases created by the Phase 1–3 schemas.
            account_columns = {row["name"] for row in conn.execute("PRAGMA table_info(operator_accounts)")}
            if "last_sync_at" not in account_columns:
                conn.execute("ALTER TABLE operator_accounts ADD COLUMN last_sync_at TEXT")
            if "last_sync_source" not in account_columns:
                conn.execute("ALTER TABLE operator_accounts ADD COLUMN last_sync_source TEXT")
            if "last_sync_counts_json" not in account_columns:
                conn.execute("ALTER TABLE operator_accounts ADD COLUMN last_sync_counts_json TEXT NOT NULL DEFAULT '{}'")
            post_columns = {row["name"] for row in conn.execute("PRAGMA table_info(historical_posts)")}
            if "data_source" not in post_columns:
                conn.execute("ALTER TABLE historical_posts ADD COLUMN data_source TEXT NOT NULL DEFAULT 'MANUAL'")
            if "source_updated_at" not in post_columns:
                conn.execute("ALTER TABLE historical_posts ADD COLUMN source_updated_at TEXT")
            if "publish_time_raw" not in post_columns:
                conn.execute("ALTER TABLE historical_posts ADD COLUMN publish_time_raw TEXT")
            if "content_type_raw" not in post_columns:
                conn.execute("ALTER TABLE historical_posts ADD COLUMN content_type_raw TEXT")
            if "source_presence" not in post_columns:
                conn.execute("ALTER TABLE historical_posts ADD COLUMN source_presence TEXT NOT NULL DEFAULT 'PRESENT'")
            if "missing_since" not in post_columns:
                conn.execute("ALTER TABLE historical_posts ADD COLUMN missing_since TEXT")
            diagnosis_columns = {row["name"] for row in conn.execute("PRAGMA table_info(account_diagnoses)")}
            if "status" not in diagnosis_columns:
                conn.execute("ALTER TABLE account_diagnoses ADD COLUMN status TEXT NOT NULL DEFAULT 'CURRENT'")
            if "stale_at" not in diagnosis_columns:
                conn.execute("ALTER TABLE account_diagnoses ADD COLUMN stale_at TEXT")
            if "stale_reason" not in diagnosis_columns:
                conn.execute("ALTER TABLE account_diagnoses ADD COLUMN stale_reason TEXT")
            conn.execute("PRAGMA user_version = 9")

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

    @staticmethod
    def _mark_diagnoses_stale(conn: sqlite3.Connection, account_id: str, now: str, reason: str) -> None:
        conn.execute(
            "UPDATE account_diagnoses SET status = 'STALE', stale_at = ?, stale_reason = ? "
            "WHERE account_id = ? AND status != 'STALE'",
            (now, reason, account_id),
        )
        conn.execute(
            "UPDATE account_baselines SET status = 'STALE' WHERE account_id = ? AND status = 'ACTIVE'",
            (account_id,),
        )

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

    def count_archived_posts(self, account_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM historical_post_archive WHERE account_id = ?", (account_id,)).fetchone()
        return int(row["total"])

    def clean_archived_legacy_titles(self, account_id: str) -> int:
        cleaned = 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT post_id, payload_json FROM historical_post_archive WHERE account_id = ?", (account_id,),
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if payload.get("data_source") != "DOUYIN_CREATOR_CENTER":
                    continue
                title = payload.get("title") or ""
                clean = clean_legacy_scan_title(title)
                if clean != title:
                    payload["title"] = clean
                    conn.execute(
                        "UPDATE historical_post_archive SET payload_json = ? WHERE account_id = ? AND post_id = ?",
                        (json.dumps(payload, ensure_ascii=False), account_id, row["post_id"]),
                    )
                    cleaned += 1
        return cleaned

    def get_sync_status(self, account_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_sync_at, last_sync_source, last_sync_counts_json "
                "FROM operator_accounts WHERE id = ?", (account_id,),
            ).fetchone()
        if row is None:
            raise AccountNotFoundError(account_id)
        return {"last_sync_at": row["last_sync_at"], "last_sync_source": row["last_sync_source"],
                "last_sync_counts": json.loads(row["last_sync_counts_json"] or "{}")}

    def record_sync(self, account_id: str, source: str, counts: dict[str, int], synced_at: str) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE operator_accounts SET last_sync_at = ?, last_sync_source = ?, "
                "last_sync_counts_json = ?, updated_at = ? WHERE id = ?",
                (synced_at, source, json.dumps(counts), synced_at, account_id),
            )
            if cursor.rowcount == 0:
                raise AccountNotFoundError(account_id)

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
            "account_id", "platform", "publish_time", "publish_time_raw", "title", "content_type", "content_type_raw", "content_source",
            "tags_json", "note", "duration", "subjects_json", "hook_type", "views", "likes",
            "comments", "favorites", "shares", "followers_gain", "profile_visits", "inquiries",
            "platform_post_id", "data_source", "source_updated_at",
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
            if inserted:
                for account_id in {values["account_id"] for post_id, values in posts if post_id in set(inserted)}:
                    self._mark_diagnoses_stale(conn, account_id, now, "historical_posts_changed")
        return inserted, duplicates

    def post_reference_counts(self, account_id: str) -> dict[str, int]:
        """Count stored diagnosis references before choosing duplicate canonicals."""
        counts: dict[str, int] = {}

        def visit(value: Any, key: str | None = None) -> None:
            if isinstance(value, dict):
                if key in {"historical_post_versions", "top_posts", "low_posts"} and isinstance(value.get("id"), str):
                    post_id = value["id"]
                    counts[post_id] = counts.get(post_id, 0) + 1
                for child_key, child in value.items():
                    visit(child, child_key)
            elif isinstance(value, list):
                if key in {"historical_post_ids", "evidence_post_ids_a", "evidence_post_ids_b"}:
                    for item in value:
                        if isinstance(item, str):
                            counts[item] = counts.get(item, 0) + 1
                else:
                    for item in value:
                        visit(item, key)
            elif key in {"historical_post_versions", "top_posts", "low_posts"} and isinstance(value, str):
                counts[value] = counts.get(value, 0) + 1

        with self._connect() as conn:
            reports = conn.execute("SELECT report_json FROM account_diagnoses WHERE account_id = ?", (account_id,)).fetchall()
        for row in reports:
            try:
                visit(json.loads(row["report_json"]))
            except (TypeError, json.JSONDecodeError):
                continue
        return counts

    @staticmethod
    def _archive_and_delete(conn: sqlite3.Connection, account_id: str, duplicate_ids: list[str],
                            canonical_id: str, now: str) -> dict[str, str]:
        id_map: dict[str, str] = {}
        for duplicate_id in duplicate_ids:
            row = conn.execute("SELECT * FROM historical_posts WHERE account_id = ? AND id = ?",
                               (account_id, duplicate_id)).fetchone()
            if row is None:
                continue
            archived_payload = dict(row)
            if archived_payload.get("data_source") == "DOUYIN_CREATOR_CENTER":
                archived_payload["title"] = clean_legacy_scan_title(archived_payload.get("title") or "")
            conn.execute(
                "INSERT OR REPLACE INTO historical_post_archive "
                "(account_id, post_id, canonical_id, payload_json, archived_at) VALUES (?, ?, ?, ?, ?)",
                (account_id, duplicate_id, canonical_id,
                 json.dumps(archived_payload, ensure_ascii=False), now),
            )
            conn.execute("DELETE FROM historical_posts WHERE account_id = ? AND id = ?",
                         (account_id, duplicate_id))
            id_map[duplicate_id] = canonical_id
        return id_map

    @staticmethod
    def _write_post(conn: sqlite3.Connection, account_id: str, post_id: str, values: dict[str, Any],
                    now: str, *, insert: bool) -> None:
        columns = (
            "account_id", "platform", "publish_time", "publish_time_raw", "title", "content_type", "content_type_raw",
            "content_source", "tags_json", "note", "duration", "subjects_json", "hook_type", "views",
            "likes", "comments", "favorites", "shares", "followers_gain", "profile_visits", "inquiries",
            "platform_post_id", "data_source", "source_updated_at", "source_presence", "missing_since",
        )
        stored = {key: value for key, value in values.items() if key in columns}
        stored["account_id"] = account_id
        stored.setdefault("source_presence", "PRESENT")
        stored.setdefault("missing_since", None)
        stored["tags_json"] = json.dumps(stored.pop("tags", values.get("tags", [])), ensure_ascii=False)
        stored["subjects_json"] = json.dumps(stored.pop("subjects", values.get("subjects", [])), ensure_ascii=False)
        params = [stored.get(column) for column in columns]
        if insert:
            conn.execute(
                f"INSERT INTO historical_posts (id, {', '.join(columns)}, created_at, updated_at) "
                f"VALUES ({', '.join('?' for _ in range(len(columns) + 3))})",
                (post_id, *params, now, now),
            )
        else:
            assignments = ", ".join(f"{column} = ?" for column in columns if column != "account_id")
            update_values = [stored.get(column) for column in columns if column != "account_id"]
            conn.execute(
                f"UPDATE historical_posts SET {assignments}, updated_at = ? WHERE account_id = ? AND id = ?",
                (*update_values, now, account_id, post_id),
            )

    @staticmethod
    def _apply_reference_remap(conn: sqlite3.Connection, account_id: str, id_map: dict[str, str]) -> None:
        if not id_map:
            return
        rows = conn.execute("SELECT id, report_json FROM account_diagnoses WHERE account_id = ?", (account_id,)).fetchall()
        for row in rows:
            try:
                report = json.loads(row["report_json"])
            except json.JSONDecodeError:
                continue
            updated = _remap_report_references(report, id_map)
            conn.execute("UPDATE account_diagnoses SET report_json = ? WHERE account_id = ? AND id = ?",
                         (json.dumps(updated, ensure_ascii=False), account_id, row["id"]))

    @staticmethod
    def _check_preview_versions(conn: sqlite3.Connection, account_id: str, base_versions: dict[str, str]) -> None:
        current = {row["id"]: row["updated_at"] for row in conn.execute(
            "SELECT id, updated_at FROM historical_posts WHERE account_id = ?", (account_id,)).fetchall()}
        if current != base_versions:
            raise ValueError("历史数据在预览后发生了变化，请重新生成预览")

    def apply_duplicate_repair(self, account_id: str, plan: dict[str, Any], now: str) -> dict[str, Any]:
        archived = 0
        id_map: dict[str, str] = {}
        with self._connect() as conn:
            self._check_preview_versions(conn, account_id, plan["base_versions"])
            for group in plan["groups"]:
                canonical_id = group["canonical_id"]
                self._write_post(conn, account_id, canonical_id, group["values"], now, insert=False)
                mapping = self._archive_and_delete(conn, account_id, group["duplicate_ids"], canonical_id, now)
                archived += len(mapping)
                id_map.update(mapping)
            self._apply_reference_remap(conn, account_id, id_map)
            if archived:
                self._mark_diagnoses_stale(conn, account_id, now, "historical_posts_deduplicated")
        return {"archived_duplicate_count": archived, "canonical_count": self.count_posts(account_id),
                "reference_remap_count": len(id_map), "diagnosis_stale": bool(archived)}

    def apply_snapshot_reconciliation(self, account_id: str, plan: dict[str, Any], now: str) -> dict[str, Any]:
        inserted = updated = archived = marked_missing = backfilled = 0
        historical_changed = False
        id_map: dict[str, str] = {}
        with self._connect() as conn:
            self._check_preview_versions(conn, account_id, plan["base_versions"])
            for operation in plan["operations"]:
                canonical_id = operation["canonical_id"] or str(__import__("uuid").uuid4())
                current = conn.execute("SELECT * FROM historical_posts WHERE account_id = ? AND id = ?",
                                       (account_id, canonical_id)).fetchone()
                if current is None:
                    self._write_post(conn, account_id, canonical_id, operation["values"], now, insert=True)
                    inserted += 1
                    historical_changed = True
                else:
                    if current["publish_time"] is None and operation["values"].get("publish_time"):
                        backfilled += 1
                    # A row matched and refreshed by a newly confirmed official
                    # export is an update event for diagnosis freshness, even when
                    # the current metric values happen to be identical.
                    historical_changed = True
                    self._write_post(conn, account_id, canonical_id, operation["values"], now, insert=False)
                    updated += 1
                mapping = self._archive_and_delete(conn, account_id, operation["duplicate_ids"], canonical_id, now)
                archived += len(mapping)
                historical_changed = historical_changed or bool(mapping)
                id_map.update(mapping)
            self._apply_reference_remap(conn, account_id, id_map)
            for post_id in plan["missing_ids"]:
                cursor = conn.execute(
                    "UPDATE historical_posts SET source_presence = 'MISSING', missing_since = COALESCE(missing_since, ?), updated_at = ? "
                    "WHERE account_id = ? AND id = ? AND source_presence != 'MISSING'",
                    (now, now, account_id, post_id),
                )
                marked_missing += cursor.rowcount
                historical_changed = historical_changed or bool(cursor.rowcount)
            if historical_changed:
                self._mark_diagnoses_stale(conn, account_id, now, "historical_snapshot_reconciled")
            counts = {"platform_unique_count": len(plan["operations"]), "inserted_count": inserted,
                      "updated_count": updated, "archived_duplicate_count": archived,
                      "platform_missing_count": marked_missing, "publish_time_backfill_count": backfilled}
            conn.execute(
                "UPDATE operator_accounts SET last_sync_at = ?, last_sync_source = ?, last_sync_counts_json = ?, updated_at = ? WHERE id = ?",
                (now, "DOUYIN_OFFICIAL_EXPORT", json.dumps(counts), now, account_id),
            )
        return {"inserted_count": inserted, "updated_count": updated, "archived_duplicate_count": archived,
                "platform_missing_count": marked_missing, "publish_time_backfill_count": backfilled,
                "canonical_count": self.count_posts(account_id), "reference_remap_count": len(id_map),
                "diagnosis_stale": historical_changed, "last_sync_at": now}

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
            self._mark_diagnoses_stale(conn, account_id, now, "historical_posts_changed")
        return self.get_post(account_id, post_id)

    def classify_posts(self, account_id: str, post_ids: list[str], values: dict[str, Any], now: str) -> int:
        allowed = {"content_source", "content_type", "subjects"}
        if not post_ids or not values or set(values) - allowed:
            raise ValueError("请选择作品并提供有效分类")
        with self._connect() as conn:
            placeholders = ",".join("?" for _ in post_ids)
            found = {row["id"] for row in conn.execute(
                f"SELECT id FROM historical_posts WHERE account_id = ? AND id IN ({placeholders})",
                (account_id, *post_ids),
            ).fetchall()}
            if found != set(post_ids):
                raise LookupError("所选作品不属于当前账号或已不存在")
            columns = {"content_source": "content_source", "content_type": "content_type", "subjects": "subjects_json"}
            for post_id in post_ids:
                assignments, params = [], []
                for field, value in values.items():
                    assignments.append(f"{columns[field]} = ?")
                    params.append(json.dumps(value, ensure_ascii=False) if field == "subjects" else value)
                conn.execute(
                    f"UPDATE historical_posts SET {', '.join(assignments)}, updated_at = ? WHERE account_id = ? AND id = ?",
                    (*params, now, account_id, post_id),
                )
            self._mark_diagnoses_stale(conn, account_id, now, "historical_posts_classified")
        return len(post_ids)

    def delete_post(self, account_id: str, post_id: str) -> bool:
        with self._connect() as conn:
            now = datetime_now_iso()
            cursor = conn.execute(
                "DELETE FROM historical_posts WHERE account_id = ? AND id = ?", (account_id, post_id)
            )
            if cursor.rowcount:
                self._mark_diagnoses_stale(conn, account_id, now, "historical_posts_changed")
            return cursor.rowcount > 0

    def save_diagnosis(self, diagnosis_id: str, account_id: str, algorithm_version: str,
                       report_json: str, generated_at: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO account_diagnoses "
                "(id, account_id, algorithm_version, report_json, generated_at) VALUES (?, ?, ?, ?, ?)",
                (diagnosis_id, account_id, algorithm_version, report_json, generated_at),
            )
            conn.execute(
                "UPDATE operator_accounts SET diagnosis_completed_at = ?, updated_at = ? WHERE id = ?",
                (generated_at, generated_at, account_id),
            )
            row = conn.execute("SELECT changes() AS changed").fetchone()
            if row["changed"] == 0:
                raise AccountNotFoundError(account_id)
        return self.get_diagnosis(account_id, diagnosis_id) or {}

    def get_latest_diagnosis(self, account_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM account_diagnoses WHERE account_id = ? "
                "ORDER BY generated_at DESC, id DESC LIMIT 1", (account_id,),
            ).fetchone()
        return self._diagnosis(row) if row else None

    def get_diagnosis(self, account_id: str, diagnosis_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM account_diagnoses WHERE account_id = ? AND id = ?",
                (account_id, diagnosis_id),
            ).fetchone()
        return self._diagnosis(row) if row else None

    @staticmethod
    def _diagnosis(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["report"] = json.loads(result.pop("report_json"))
        return result

    def list_diagnoses(self, account_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM account_diagnoses WHERE account_id = ? "
                "ORDER BY generated_at DESC, id DESC LIMIT ?", (account_id, limit),
            ).fetchall()
        return [self._diagnosis(row) for row in rows]

    @staticmethod
    def _baseline(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        report = json.loads(result.pop("report_json"))
        result.update(report)
        return result

    def get_latest_baseline(self, account_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM account_baselines WHERE account_id = ? ORDER BY version DESC LIMIT 1",
                (account_id,),
            ).fetchone()
        return self._baseline(row) if row else None

    def list_baselines(self, account_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM account_baselines WHERE account_id = ? ORDER BY version DESC LIMIT ?",
                (account_id, limit),
            ).fetchall()
        return [self._baseline(row) for row in rows]

    def mark_baseline_stale(self, account_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE account_baselines SET status = 'STALE' WHERE account_id = ? AND status = 'ACTIVE'",
                (account_id,),
            )

    def save_baseline(self, baseline_id: str, account_id: str, sample_size: int,
                      period_start: str | None, period_end: str | None, generated_at: str,
                      source_updated_at: str | None, historical_data_version: str,
                      report: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            account = conn.execute("SELECT 1 FROM operator_accounts WHERE id = ?", (account_id,)).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            conn.execute("UPDATE account_baselines SET status = 'STALE' WHERE account_id = ? AND status = 'ACTIVE'",
                         (account_id,))
            version = int(conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM account_baselines WHERE account_id = ?",
                (account_id,),
            ).fetchone()["next_version"])
            conn.execute(
                "INSERT INTO account_baselines "
                "(id, account_id, version, sample_size, period_start, period_end, generated_at, "
                "source_updated_at, historical_data_version, status, report_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)",
                (baseline_id, account_id, version, sample_size, period_start, period_end, generated_at,
                 source_updated_at, historical_data_version, json.dumps(report, ensure_ascii=False, allow_nan=False)),
            )
        return self.get_latest_baseline(account_id) or {}
