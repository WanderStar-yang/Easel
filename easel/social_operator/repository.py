"""SQLite persistence for isolated Social Operator V1 business data."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from uuid import uuid4
from .canonical import clean_title

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "outputs" / "_social_operator.sqlite3"
CONTENT_TYPE_LABELS = {
    "单猫日常", "双猫互动", "双猫反差", "搞笑/趣味", "养猫经验", "情绪/陪伴", "AI创意", "其他",
}
SUBJECT_LABELS = {"缅因", "布偶", "双猫", "其他", "UNKNOWN"}


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
                CREATE TABLE IF NOT EXISTS strategy_recommendations (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    baseline_id TEXT,
                    baseline_version INTEGER,
                    diagnosis_id TEXT,
                    generated_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('CURRENT', 'SUPERSEDED', 'STALE')),
                    evidence_data_version TEXT,
                    recommendation_json TEXT NOT NULL,
                    UNIQUE(account_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_strategy_recommendations_history
                    ON strategy_recommendations(account_id, version DESC);
                CREATE TABLE IF NOT EXISTS operator_active_strategies (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    source_recommendation_id TEXT NOT NULL REFERENCES strategy_recommendations(id),
                    version INTEGER NOT NULL CHECK (version >= 1),
                    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUPERSEDED')),
                    positioning TEXT NOT NULL,
                    target_audience TEXT NOT NULL,
                    content_pillars_json TEXT NOT NULL,
                    experiment_plan_json TEXT NOT NULL,
                    confidence_at_confirmation TEXT NOT NULL CHECK (confidence_at_confirmation IN ('LOW', 'MEDIUM', 'HIGH')),
                    confirmed_at TEXT NOT NULL,
                    confirmed_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(account_id, version)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_operator_active_strategy_one_active
                    ON operator_active_strategies(account_id) WHERE status = 'ACTIVE';
                CREATE INDEX IF NOT EXISTS idx_operator_active_strategy_history
                    ON operator_active_strategies(account_id, version DESC);
                CREATE TABLE IF NOT EXISTS operator_content_pillars (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    strategy_id TEXT NOT NULL REFERENCES operator_active_strategies(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    allocation_ratio INTEGER NOT NULL CHECK (allocation_ratio BETWEEN 0 AND 100),
                    goal TEXT NOT NULL,
                    experiment_question TEXT NOT NULL,
                    evidence_summary_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUPERSEDED')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_operator_content_pillars_strategy
                    ON operator_content_pillars(account_id, strategy_id, status);
                CREATE TABLE IF NOT EXISTS strategy_confirmation_events (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    recommendation_id TEXT NOT NULL REFERENCES strategy_recommendations(id),
                    strategy_id TEXT NOT NULL REFERENCES operator_active_strategies(id),
                    event_type TEXT NOT NULL CHECK (event_type = 'STRATEGY_CONFIRMED'),
                    confirmed_at TEXT NOT NULL,
                    pillar_ratios_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_strategy_confirmation_events_account
                    ON strategy_confirmation_events(account_id, confirmed_at DESC);
                CREATE TABLE IF NOT EXISTS strategy_active_change_events (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    strategy_id TEXT NOT NULL REFERENCES operator_active_strategies(id),
                    event_type TEXT NOT NULL CHECK (event_type = 'EXPERIMENT_PLAN_REPAIRED'),
                    reason TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operator_topic_batches (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    strategy_id TEXT NOT NULL REFERENCES operator_active_strategies(id),
                    local_date TEXT NOT NULL,
                    batch_number INTEGER NOT NULL CHECK (batch_number >= 1),
                    generated_at TEXT NOT NULL,
                    generation_mode TEXT NOT NULL CHECK (generation_mode IN ('AI', 'TEMPLATE')),
                    status TEXT NOT NULL CHECK (status IN ('CURRENT', 'SUPERSEDED')),
                    UNIQUE(account_id, local_date, batch_number)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_operator_topic_one_current_batch
                    ON operator_topic_batches(account_id, local_date) WHERE status = 'CURRENT';
                CREATE INDEX IF NOT EXISTS idx_operator_topic_batch_history
                    ON operator_topic_batches(account_id, local_date DESC, batch_number DESC);
                CREATE TABLE IF NOT EXISTS operator_topics (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES operator_topic_batches(id) ON DELETE CASCADE,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    strategy_id TEXT NOT NULL REFERENCES operator_active_strategies(id),
                    pillar_id TEXT NOT NULL REFERENCES operator_content_pillars(id),
                    title TEXT NOT NULL,
                    angle TEXT NOT NULL,
                    description TEXT NOT NULL,
                    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
                    score_breakdown_json TEXT NOT NULL,
                    recommendation_reason TEXT NOT NULL,
                    historical_evidence_json TEXT NOT NULL,
                    experiment_question TEXT NOT NULL,
                    production_difficulty TEXT NOT NULL CHECK (production_difficulty IN ('EASY', 'MEDIUM', 'HARD')),
                    material_requirements_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('CANDIDATE', 'RECOMMENDED', 'SELECTED', 'REJECTED', 'SKIPPED')),
                    similarity_score REAL NOT NULL DEFAULT 0 CHECK (similarity_score BETWEEN 0 AND 1),
                    created_at TEXT NOT NULL,
                    UNIQUE(batch_id, title)
                );
                CREATE INDEX IF NOT EXISTS idx_operator_topics_account_status
                    ON operator_topics(account_id, status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_operator_topics_pillar_history
                    ON operator_topics(account_id, pillar_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS operator_topic_events (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    topic_id TEXT REFERENCES operator_topics(id) ON DELETE SET NULL,
                    batch_id TEXT REFERENCES operator_topic_batches(id) ON DELETE SET NULL,
                    event_type TEXT NOT NULL CHECK (event_type IN ('TOPIC_SELECTED', 'BATCH_REPLACED')),
                    occurred_at TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_operator_topic_events_account
                    ON operator_topic_events(account_id, occurred_at DESC);
                CREATE TABLE IF NOT EXISTS operator_content_drafts (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    topic_id TEXT NOT NULL REFERENCES operator_topics(id) ON DELETE CASCADE,
                    strategy_id TEXT NOT NULL REFERENCES operator_active_strategies(id),
                    strategy_version INTEGER NOT NULL CHECK (strategy_version >= 1),
                    version INTEGER NOT NULL CHECK (version >= 1),
                    platform TEXT NOT NULL CHECK (platform IN ('douyin', 'xiaohongshu')),
                    generation_mode TEXT NOT NULL CHECK (generation_mode = 'AI'),
                    status TEXT NOT NULL CHECK (status IN ('CURRENT', 'SUPERSEDED')),
                    content_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(topic_id, version)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_operator_content_draft_one_current
                    ON operator_content_drafts(account_id, topic_id) WHERE status = 'CURRENT';
                CREATE INDEX IF NOT EXISTS idx_operator_content_drafts_account
                    ON operator_content_drafts(account_id, generated_at DESC);
                CREATE TABLE IF NOT EXISTS operator_content_draft_events (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    draft_id TEXT NOT NULL REFERENCES operator_content_drafts(id) ON DELETE CASCADE,
                    topic_id TEXT NOT NULL REFERENCES operator_topics(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL CHECK (event_type IN ('GENERATED', 'EDITED', 'REGENERATED')),
                    occurred_at TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_operator_content_draft_events_account
                    ON operator_content_draft_events(account_id, occurred_at DESC);
                CREATE TABLE IF NOT EXISTS operator_published_posts (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    topic_id TEXT REFERENCES operator_topics(id) ON DELETE SET NULL,
                    draft_id TEXT REFERENCES operator_content_drafts(id) ON DELETE SET NULL,
                    strategy_id TEXT NOT NULL REFERENCES operator_active_strategies(id),
                    strategy_version INTEGER NOT NULL CHECK (strategy_version >= 1),
                    platform TEXT NOT NULL CHECK (platform IN ('douyin', 'xiaohongshu')),
                    platform_post_id TEXT,
                    title TEXT NOT NULL,
                    published_url TEXT,
                    published_at TEXT NOT NULL,
                    content_source TEXT NOT NULL CHECK (content_source IN ('REAL', 'AI', 'MIXED', 'UNKNOWN')),
                    hook_type TEXT,
                    duration_seconds INTEGER CHECK (duration_seconds IS NULL OR duration_seconds > 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(id, account_id)
                );
                CREATE INDEX IF NOT EXISTS idx_operator_published_posts_account_time
                    ON operator_published_posts(account_id, published_at DESC);
                CREATE TABLE IF NOT EXISTS operator_post_metrics (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    published_post_id TEXT NOT NULL,
                    checkpoint TEXT NOT NULL CHECK (checkpoint IN ('24H', '72H', '7D')),
                    views INTEGER CHECK (views IS NULL OR views >= 0),
                    likes INTEGER CHECK (likes IS NULL OR likes >= 0),
                    comments INTEGER CHECK (comments IS NULL OR comments >= 0),
                    favorites INTEGER CHECK (favorites IS NULL OR favorites >= 0),
                    shares INTEGER CHECK (shares IS NULL OR shares >= 0),
                    followers_gain INTEGER,
                    profile_visits INTEGER CHECK (profile_visits IS NULL OR profile_visits >= 0),
                    inquiries INTEGER CHECK (inquiries IS NULL OR inquiries >= 0),
                    recorded_at TEXT NOT NULL,
                    UNIQUE(published_post_id, checkpoint),
                    FOREIGN KEY(published_post_id, account_id)
                        REFERENCES operator_published_posts(id, account_id) ON DELETE CASCADE,
                    CHECK (views IS NOT NULL OR likes IS NOT NULL OR comments IS NOT NULL OR favorites IS NOT NULL
                           OR shares IS NOT NULL OR followers_gain IS NOT NULL OR profile_visits IS NOT NULL
                           OR inquiries IS NOT NULL)
                );
                CREATE INDEX IF NOT EXISTS idx_operator_post_metrics_account_post
                    ON operator_post_metrics(account_id, published_post_id, checkpoint);
                CREATE TABLE IF NOT EXISTS operator_weekly_reviews (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL CHECK (version >= 1),
                    week_start TEXT NOT NULL,
                    week_end TEXT NOT NULL,
                    baseline_id TEXT REFERENCES account_baselines(id),
                    baseline_version INTEGER,
                    source_data_version TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('CURRENT', 'STALE', 'SUPERSEDED')),
                    generated_at TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    UNIQUE(account_id, week_start, version)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_operator_weekly_review_one_current
                    ON operator_weekly_reviews(account_id, week_start) WHERE status = 'CURRENT';
                CREATE INDEX IF NOT EXISTS idx_operator_weekly_reviews_history
                    ON operator_weekly_reviews(account_id, week_start DESC, version DESC);
                CREATE TABLE IF NOT EXISTS operator_strategy_memories (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    review_id TEXT NOT NULL REFERENCES operator_weekly_reviews(id),
                    memory_key TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version >= 1),
                    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'ACTIVE', 'SUPERSEDED', 'DISMISSED', 'STALE')),
                    statement TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    confirmed_by TEXT,
                    UNIQUE(account_id, memory_key, version)
                );
                CREATE INDEX IF NOT EXISTS idx_operator_strategy_memories_active
                    ON operator_strategy_memories(account_id, status, created_at DESC);
                CREATE TABLE IF NOT EXISTS operator_strategy_memory_events (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    memory_id TEXT NOT NULL REFERENCES operator_strategy_memories(id),
                    review_id TEXT NOT NULL REFERENCES operator_weekly_reviews(id),
                    event_type TEXT NOT NULL CHECK (event_type IN ('CONFIRMED', 'DISMISSED', 'SUPERSEDED', 'STALE')),
                    occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_operator_memory_events_account
                    ON operator_strategy_memory_events(account_id, occurred_at DESC);
                CREATE TABLE IF NOT EXISTS operator_content_calendar (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    topic_id TEXT NOT NULL REFERENCES operator_topics(id),
                    draft_id TEXT REFERENCES operator_content_drafts(id) ON DELETE SET NULL,
                    strategy_id TEXT NOT NULL REFERENCES operator_active_strategies(id),
                    strategy_version INTEGER NOT NULL CHECK (strategy_version >= 1),
                    platform TEXT NOT NULL CHECK (platform IN ('douyin', 'xiaohongshu')),
                    status TEXT NOT NULL CHECK (status IN ('SELECTED', 'DRAFT', 'READY', 'PUBLISHED', 'REVIEWED', 'CANCELLED')),
                    planned_publish_at TEXT NOT NULL,
                    actual_publish_at TEXT,
                    published_url TEXT,
                    published_post_id TEXT REFERENCES operator_published_posts(id) ON DELETE SET NULL,
                    review_id TEXT REFERENCES operator_weekly_reviews(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_operator_calendar_active_topic
                    ON operator_content_calendar(account_id, topic_id) WHERE status != 'CANCELLED';
                CREATE INDEX IF NOT EXISTS idx_operator_calendar_account_date
                    ON operator_content_calendar(account_id, planned_publish_at, status);
                CREATE INDEX IF NOT EXISTS idx_operator_calendar_published_post
                    ON operator_content_calendar(account_id, published_post_id);
                CREATE TABLE IF NOT EXISTS operator_content_calendar_events (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    calendar_item_id TEXT NOT NULL REFERENCES operator_content_calendar(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL CHECK (event_type IN ('SCHEDULED', 'RESCHEDULED', 'READY', 'CANCELLED', 'PUBLISHED', 'REVIEWED', 'REVIEW_INVALIDATED')),
                    occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_operator_calendar_events_account
                    ON operator_content_calendar_events(account_id, occurred_at DESC);
                CREATE TABLE IF NOT EXISTS historical_post_classification_metadata (
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    post_id TEXT NOT NULL REFERENCES historical_posts(id) ON DELETE CASCADE,
                    field TEXT NOT NULL CHECK (field IN ('content_source', 'subjects', 'content_type')),
                    value_json TEXT NOT NULL DEFAULT 'null',
                    source TEXT NOT NULL CHECK (source IN ('IMPORT', 'AI_CONFIRMED', 'MANUAL_CONFIRMED')),
                    confidence TEXT CHECK (confidence IS NULL OR confidence IN ('HIGH', 'MEDIUM', 'LOW')),
                    confirmed_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (post_id, field)
                );
                CREATE TABLE IF NOT EXISTS historical_post_classification_suggestions (
                    account_id TEXT NOT NULL REFERENCES operator_accounts(id) ON DELETE CASCADE,
                    post_id TEXT NOT NULL REFERENCES historical_posts(id) ON DELETE CASCADE,
                    suggestions_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'SUGGESTED' CHECK (status IN ('SUGGESTED', 'CONFIRMED')),
                    generated_at TEXT NOT NULL,
                    PRIMARY KEY (post_id)
                );
                CREATE INDEX IF NOT EXISTS idx_classification_suggestions_account
                    ON historical_post_classification_suggestions(account_id, status, generated_at DESC);
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
            classification_columns = {row["name"] for row in conn.execute(
                "PRAGMA table_info(historical_post_classification_metadata)")}
            if "value_json" not in classification_columns:
                conn.execute("ALTER TABLE historical_post_classification_metadata "
                             "ADD COLUMN value_json TEXT NOT NULL DEFAULT 'null'")
            # Preserve known legacy classifications and their origin. Manual
            # records are treated as user-confirmed; imported values remain
            # traceable as imports and can be reviewed against V1 labels.
            for field, column, predicate in (
                ("content_source", "content_source", "content_source != 'UNKNOWN'"),
                ("content_type", "content_type", "content_type IS NOT NULL AND TRIM(content_type) != ''"),
                ("subjects", "subjects_json", "subjects_json != '[]'"),
            ):
                legacy_rows = conn.execute(
                    f"SELECT account_id, id, {column} AS value, data_source, updated_at "
                    f"FROM historical_posts WHERE {predicate}"
                ).fetchall()
                for row in legacy_rows:
                    if field == "subjects":
                        try:
                            value = json.loads(row["value"] or "[]")
                        except json.JSONDecodeError:
                            value = []
                    else:
                        value = row["value"]
                    origin = "MANUAL_CONFIRMED" if row["data_source"] == "MANUAL" else "IMPORT"
                    conn.execute(
                        "INSERT OR IGNORE INTO historical_post_classification_metadata "
                        "(account_id, post_id, field, value_json, source, confidence, confirmed_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                        (row["account_id"], row["id"], field, json.dumps(value, ensure_ascii=False), origin,
                         row["updated_at"] if origin == "MANUAL_CONFIRMED" else None, row["updated_at"]),
                    )
            # Upgrade metadata created by an early Phase 4.5 schema before values were stored alongside origin.
            stale_metadata = conn.execute(
                "SELECT account_id, post_id, field FROM historical_post_classification_metadata "
                "WHERE value_json = 'null'"
            ).fetchall()
            for row in stale_metadata:
                value_row = conn.execute(
                    f"SELECT {'subjects_json' if row['field'] == 'subjects' else row['field']} AS value "
                    "FROM historical_posts WHERE account_id = ? AND id = ?",
                    (row["account_id"], row["post_id"]),
                ).fetchone()
                if value_row:
                    value = json.loads(value_row["value"] or "[]") if row["field"] == "subjects" else value_row["value"]
                    conn.execute("UPDATE historical_post_classification_metadata SET value_json = ? "
                                 "WHERE account_id = ? AND post_id = ? AND field = ?",
                                 (json.dumps(value, ensure_ascii=False), row["account_id"], row["post_id"], row["field"]))
            published_columns = {row["name"] for row in conn.execute("PRAGMA table_info(operator_published_posts)")}
            if "platform_post_id" not in published_columns:
                conn.execute("ALTER TABLE operator_published_posts ADD COLUMN platform_post_id TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_operator_published_posts_platform_id "
                "ON operator_published_posts(account_id, platform_post_id) "
                "WHERE platform_post_id IS NOT NULL AND platform_post_id != ''"
            )
            conn.execute("PRAGMA user_version = 17")

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
        active_strategy = row["active_strategy"]
        return {
            "id": row["id"], "name": row["name"], "platform": row["platform"],
            "status": row["status"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "diagnosis_completed_at": row["diagnosis_completed_at"],
            "profile": json.loads(profile) if profile else None,
            "strategy": json.loads(strategy) if strategy else None,
            "active_strategy": json.loads(active_strategy) if active_strategy else None,
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
                    FROM operator_strategies s WHERE s.account_id = a.id) AS strategy,
                (SELECT json_object('id', active.id, 'version', active.version, 'status', active.status,
                    'confirmedAt', active.confirmed_at,
                    'confidenceAtConfirmation', active.confidence_at_confirmation)
                    FROM operator_active_strategies active
                    WHERE active.account_id = a.id AND active.status = 'ACTIVE') AS active_strategy
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
                origin = "MANUAL_CONFIRMED" if stored.get("data_source") == "MANUAL" else "IMPORT"
                for field in ("content_source", "content_type", "subjects"):
                    if field == "subjects":
                        value = json.loads(stored.get("subjects_json") or "[]")
                        present = bool(value)
                    else:
                        value = stored.get(field)
                        present = value not in (None, "", "UNKNOWN")
                    if present:
                        self._set_classification_metadata(
                            conn, stored["account_id"], post_id, field, origin, None,
                            now if origin == "MANUAL_CONFIRMED" else None, now,
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
            for field in {"content_source", "content_type", "subjects"} & values.keys():
                self._set_classification_metadata(conn, account_id, post_id, field,
                                                  "MANUAL_CONFIRMED", None, now, now)
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
                for field in values:
                    self._set_classification_metadata(conn, account_id, post_id, field,
                                                      "MANUAL_CONFIRMED", None, now, now)
            self._mark_diagnoses_stale(conn, account_id, now, "historical_posts_classified")
        return len(post_ids)

    @staticmethod
    def _set_classification_metadata(conn: sqlite3.Connection, account_id: str, post_id: str, field: str,
                                     source: str, confidence: str | None, confirmed_at: str | None,
                                     updated_at: str) -> None:
        column = {"content_source": "content_source", "subjects": "subjects_json", "content_type": "content_type"}[field]
        value_row = conn.execute(f"SELECT {column} AS value FROM historical_posts WHERE account_id = ? AND id = ?",
                                 (account_id, post_id)).fetchone()
        raw_value = value_row["value"] if value_row else None
        value = json.loads(raw_value or "[]") if field == "subjects" else raw_value
        conn.execute(
            "INSERT INTO historical_post_classification_metadata "
            "(account_id, post_id, field, value_json, source, confidence, confirmed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(post_id, field) DO UPDATE SET "
            "account_id = excluded.account_id, value_json = excluded.value_json, source = excluded.source, confidence = excluded.confidence, "
            "confirmed_at = excluded.confirmed_at, updated_at = excluded.updated_at",
            (account_id, post_id, field, json.dumps(value, ensure_ascii=False), source, confidence, confirmed_at, updated_at),
        )

    def save_classification_suggestions(self, account_id: str, suggestions: dict[str, dict[str, Any]],
                                        generated_at: str) -> int:
        if not suggestions:
            return 0
        with self._connect() as conn:
            post_ids = list(suggestions)
            placeholders = ",".join("?" for _ in post_ids)
            rows = conn.execute(
                f"SELECT id FROM historical_posts WHERE account_id = ? AND id IN ({placeholders})",
                (account_id, *post_ids),
            ).fetchall()
            if {row["id"] for row in rows} != set(post_ids):
                raise LookupError("作品不属于当前账号或已不存在")
            metadata = conn.execute(
                f"SELECT post_id, field, source FROM historical_post_classification_metadata "
                f"WHERE account_id = ? AND post_id IN ({placeholders})",
                (account_id, *post_ids),
            ).fetchall()
            manual = {(row["post_id"], row["field"]) for row in metadata
                      if row["source"] == "MANUAL_CONFIRMED"}
            for post_id, fields in suggestions.items():
                safe_fields = {field: item for field, item in fields.items()
                               if (post_id, field) not in manual}
                conn.execute(
                    "INSERT INTO historical_post_classification_suggestions "
                    "(account_id, post_id, suggestions_json, status, generated_at) VALUES (?, ?, ?, 'SUGGESTED', ?) "
                    "ON CONFLICT(post_id) DO UPDATE SET account_id = excluded.account_id, "
                    "suggestions_json = excluded.suggestions_json, status = 'SUGGESTED', generated_at = excluded.generated_at",
                    (account_id, post_id, json.dumps(safe_fields, ensure_ascii=False, allow_nan=False), generated_at),
                )
        return len(suggestions)

    def get_classification_overlay(self, account_id: str, post_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not post_ids:
            return {}
        placeholders = ",".join("?" for _ in post_ids)
        with self._connect() as conn:
            metadata = conn.execute(
                f"SELECT post_id, field, value_json, source, confidence, confirmed_at FROM historical_post_classification_metadata "
                f"WHERE account_id = ? AND post_id IN ({placeholders})", (account_id, *post_ids),
            ).fetchall()
            suggestions = conn.execute(
                f"SELECT post_id, suggestions_json, status, generated_at FROM historical_post_classification_suggestions "
                f"WHERE account_id = ? AND post_id IN ({placeholders})", (account_id, *post_ids),
            ).fetchall()
        result = {post_id: {"metadata": {}, "suggestions": {}, "suggestion_status": None,
                            "suggested_at": None} for post_id in post_ids}
        for row in metadata:
            result[row["post_id"]]["metadata"][row["field"]] = {
                "value": json.loads(row["value_json"]), "source": row["source"],
                "confidence": row["confidence"], "confirmed_at": row["confirmed_at"]}
        for row in suggestions:
            result[row["post_id"]].update({
                "suggestions": json.loads(row["suggestions_json"]),
                "suggestion_status": row["status"], "suggested_at": row["generated_at"],
            })
        return result

    def accept_classification_suggestions(self, account_id: str, post_ids: list[str], fields: list[str],
                                          now: str, *, high_confidence_only: bool = False) -> dict[str, int]:
        allowed = {"content_source", "subjects", "content_type"}
        if not post_ids or not fields or set(fields) - allowed:
            raise ValueError("请选择作品和分类字段")
        columns = {"content_source": "content_source", "subjects": "subjects_json", "content_type": "content_type"}
        accepted_posts: set[str] = set()
        accepted_fields = 0
        with self._connect() as conn:
            placeholders = ",".join("?" for _ in post_ids)
            posts = conn.execute(
                f"SELECT id FROM historical_posts WHERE account_id = ? AND id IN ({placeholders})",
                (account_id, *post_ids),
            ).fetchall()
            if {row["id"] for row in posts} != set(post_ids):
                raise LookupError("作品不属于当前账号或已不存在")
            for post_id in post_ids:
                row = conn.execute(
                    "SELECT suggestions_json FROM historical_post_classification_suggestions "
                    "WHERE account_id = ? AND post_id = ? AND status = 'SUGGESTED'", (account_id, post_id),
                ).fetchone()
                if row is None:
                    continue
                suggestions = json.loads(row["suggestions_json"])
                current_fields = dict(suggestions)
                for field in fields:
                    item = suggestions.get(field)
                    if not isinstance(item, dict):
                        continue
                    if high_confidence_only and item.get("confidence") != "HIGH":
                        continue
                    metadata = conn.execute(
                        "SELECT source FROM historical_post_classification_metadata "
                        "WHERE account_id = ? AND post_id = ? AND field = ?", (account_id, post_id, field),
                    ).fetchone()
                    if metadata and metadata["source"] == "MANUAL_CONFIRMED":
                        current_fields.pop(field, None)
                        continue
                    value = item.get("value")
                    if field == "content_source":
                        if value not in {"REAL", "AI", "MIXED"}:
                            current_fields.pop(field, None)
                            continue
                    elif field == "content_type":
                        if value not in CONTENT_TYPE_LABELS:
                            current_fields.pop(field, None)
                            continue
                    elif field == "subjects":
                        if value not in SUBJECT_LABELS:
                            current_fields.pop(field, None)
                            continue
                        value = [value] if value != "UNKNOWN" else []
                    encoded = json.dumps(value, ensure_ascii=False) if field == "subjects" else value
                    conn.execute(f"UPDATE historical_posts SET {columns[field]} = ?, updated_at = ? "
                                 "WHERE account_id = ? AND id = ?", (encoded, now, account_id, post_id))
                    self._set_classification_metadata(conn, account_id, post_id, field, "AI_CONFIRMED",
                                                      item.get("confidence"), now, now)
                    current_fields.pop(field, None)
                    accepted_posts.add(post_id)
                    accepted_fields += 1
                status = "SUGGESTED" if current_fields else "CONFIRMED"
                conn.execute(
                    "UPDATE historical_post_classification_suggestions SET suggestions_json = ?, status = ? "
                    "WHERE account_id = ? AND post_id = ?",
                    (json.dumps(current_fields, ensure_ascii=False), status, account_id, post_id),
                )
            if accepted_posts:
                self._mark_diagnoses_stale(conn, account_id, now, "historical_posts_classified")
        return {"updated_count": len(accepted_posts), "confirmed_field_count": accepted_fields}

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

    @staticmethod
    def _strategy_recommendation(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["recommendation"] = json.loads(result.pop("recommendation_json"))
        return result

    def save_strategy_recommendation(self, recommendation_id: str, account_id: str, *,
                                     baseline_id: str | None, baseline_version: int | None,
                                     diagnosis_id: str | None, generated_at: str,
                                     evidence_data_version: str | None,
                                     recommendation: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM operator_accounts WHERE id = ?", (account_id,)).fetchone() is None:
                raise AccountNotFoundError(account_id)
            conn.execute("UPDATE strategy_recommendations SET status = 'SUPERSEDED' "
                         "WHERE account_id = ? AND status = 'CURRENT'", (account_id,))
            version = int(conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
                "FROM strategy_recommendations WHERE account_id = ?", (account_id,),
            ).fetchone()["next_version"])
            conn.execute(
                "INSERT INTO strategy_recommendations "
                "(id, account_id, version, baseline_id, baseline_version, diagnosis_id, generated_at, "
                "status, evidence_data_version, recommendation_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'CURRENT', ?, ?)",
                (recommendation_id, account_id, version, baseline_id, baseline_version, diagnosis_id,
                 generated_at, evidence_data_version,
                 json.dumps(recommendation, ensure_ascii=False, allow_nan=False)),
            )
            row = conn.execute("SELECT * FROM strategy_recommendations WHERE id = ?", (recommendation_id,)).fetchone()
        return self._strategy_recommendation(row)

    def get_latest_strategy_recommendation(self, account_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM strategy_recommendations WHERE account_id = ? "
                               "ORDER BY version DESC LIMIT 1", (account_id,)).fetchone()
        return self._strategy_recommendation(row) if row else None

    def list_strategy_recommendations(self, account_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM strategy_recommendations WHERE account_id = ? "
                                "ORDER BY version DESC LIMIT ?", (account_id, limit)).fetchall()
        return [self._strategy_recommendation(row) for row in rows]

    def mark_strategy_recommendation_stale(self, recommendation_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE strategy_recommendations SET status = 'STALE' "
                         "WHERE id = ? AND status = 'CURRENT'", (recommendation_id,))

    @staticmethod
    def _active_strategy(row: sqlite3.Row, pillars: list[sqlite3.Row]) -> dict[str, Any]:
        result = dict(row)
        result["content_pillars"] = json.loads(result.pop("content_pillars_json"))
        result["experiment_plan"] = json.loads(result.pop("experiment_plan_json"))
        result["pillars"] = []
        for pillar in pillars:
            item = dict(pillar)
            item["evidence_summary"] = json.loads(item.pop("evidence_summary_json"))
            result["pillars"].append(item)
        return result

    def confirm_strategy(self, account_id: str, recommendation_id: str, *, positioning: str,
                         target_audience: str, pillars: list[dict[str, Any]],
                         experiment_plan: dict[str, Any], confidence: str,
                         confirmed_by: str, now: str) -> dict[str, Any]:
        """Atomically preserve a recommendation and activate a user-confirmed strategy."""
        strategy_id = f"active-strategy-{uuid4().hex}"
        pillar_ids = [f"pillar-{uuid4().hex}" for _ in pillars]
        audit_id = f"strategy-confirmation-{uuid4().hex}"
        with self._connect() as conn:
            account = conn.execute(
                "SELECT a.*, s.state AS strategy_state FROM operator_accounts a "
                "JOIN operator_strategies s ON s.account_id = a.id WHERE a.id = ?",
                (account_id,),
            ).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            if account["status"] == "ACTIVE":
                raise ValueError("该账号已经启用策略；请创建新版本后再调整。")
            if account["status"] not in {"NEW", "DIAGNOSING", "STRATEGY_PENDING_CONFIRMATION"}:
                raise ValueError("当前账号状态不允许确认策略。")

            recommendation_row = conn.execute(
                "SELECT * FROM strategy_recommendations WHERE id = ? AND account_id = ?",
                (recommendation_id, account_id),
            ).fetchone()
            if recommendation_row is None:
                raise ValueError("策略建议不存在或不属于当前账号。")
            latest = conn.execute(
                "SELECT id, status FROM strategy_recommendations WHERE account_id = ? "
                "ORDER BY version DESC LIMIT 1", (account_id,),
            ).fetchone()
            if (recommendation_row["status"] != "CURRENT" or latest is None
                    or latest["id"] != recommendation_id or latest["status"] != "CURRENT"):
                raise ValueError("策略建议已过期，请重新查看最新建议。")
            recommendation = json.loads(recommendation_row["recommendation_json"])
            sample_size = int((recommendation.get("source") or {}).get("canonical_sample_size") or 0)
            baseline_id = recommendation_row["baseline_id"]
            diagnosis_id = recommendation_row["diagnosis_id"]
            if sample_size > 0:
                if not baseline_id or not diagnosis_id or not account["diagnosis_completed_at"]:
                    raise ValueError("有历史作品的账号需要有效 Baseline 和完成的 Diagnosis 才能确认。")
                baseline = conn.execute(
                    "SELECT status FROM account_baselines WHERE id = ? AND account_id = ?",
                    (baseline_id, account_id),
                ).fetchone()
                diagnosis = conn.execute(
                    "SELECT status FROM account_diagnoses WHERE id = ? AND account_id = ?",
                    (diagnosis_id, account_id),
                ).fetchone()
                if baseline is None or baseline["status"] != "ACTIVE":
                    raise ValueError("历史基准已过期，请先更新 Baseline。")
                if diagnosis is None or diagnosis["status"] != "CURRENT":
                    raise ValueError("账号诊断已过期，请先重新诊断。")
            else:
                historical_rows = conn.execute(
                    "SELECT COUNT(*) AS count FROM historical_posts WHERE account_id = ?", (account_id,),
                ).fetchone()["count"]
                if (account["platform"] != "xiaohongshu" or baseline_id is not None
                        or historical_rows != 0):
                    raise ValueError("只有没有历史数据的小红书账号可以使用起步实验策略确认。")

            active = conn.execute(
                "SELECT 1 FROM operator_active_strategies WHERE account_id = ? AND status = 'ACTIVE'",
                (account_id,),
            ).fetchone()
            if active:
                raise ValueError("该账号已经存在 ACTIVE Strategy。")
            version = int(conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
                "FROM operator_active_strategies WHERE account_id = ?", (account_id,),
            ).fetchone()["next_version"])
            pillar_snapshot = []
            for pillar_id, pillar in zip(pillar_ids, pillars):
                pillar_snapshot.append({
                    "id": pillar_id, "name": pillar["name"], "description": pillar["description"],
                    "allocation_ratio": pillar["allocation_ratio"], "goal": pillar["goal"],
                    "experiment_question": pillar["experiment_question"],
                    "evidence_summary": pillar["evidence_summary"], "status": "ACTIVE",
                })
            conn.execute(
                "UPDATE operator_active_strategies SET status = 'SUPERSEDED', updated_at = ? "
                "WHERE account_id = ? AND status = 'ACTIVE'", (now, account_id),
            )
            conn.execute(
                "UPDATE operator_content_pillars SET status = 'SUPERSEDED', updated_at = ? "
                "WHERE account_id = ? AND status = 'ACTIVE'", (now, account_id),
            )
            conn.execute(
                "INSERT INTO operator_active_strategies "
                "(id, account_id, source_recommendation_id, version, status, positioning, target_audience, "
                "content_pillars_json, experiment_plan_json, confidence_at_confirmation, confirmed_at, "
                "confirmed_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (strategy_id, account_id, recommendation_id, version, positioning, target_audience,
                 json.dumps(pillar_snapshot, ensure_ascii=False, allow_nan=False),
                 json.dumps(experiment_plan, ensure_ascii=False, allow_nan=False), confidence, now,
                 confirmed_by, now, now),
            )
            for pillar_id, pillar in zip(pillar_ids, pillars):
                conn.execute(
                    "INSERT INTO operator_content_pillars "
                    "(id, account_id, strategy_id, name, description, allocation_ratio, goal, "
                    "experiment_question, evidence_summary_json, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)",
                    (pillar_id, account_id, strategy_id, pillar["name"], pillar["description"],
                     pillar["allocation_ratio"], pillar["goal"], pillar["experiment_question"],
                     json.dumps(pillar["evidence_summary"], ensure_ascii=False, allow_nan=False), now, now),
                )
            conn.execute(
                "INSERT INTO strategy_confirmation_events "
                "(id, account_id, recommendation_id, strategy_id, event_type, confirmed_at, pillar_ratios_json) "
                "VALUES (?, ?, ?, ?, 'STRATEGY_CONFIRMED', ?, ?)",
                (audit_id, account_id, recommendation_id, strategy_id, now,
                 json.dumps([p["allocation_ratio"] for p in pillars], ensure_ascii=False)),
            )
            conn.execute(
                "UPDATE operator_strategies SET summary = ?, state = 'confirmed', confirmed_at = ? "
                "WHERE account_id = ?", (positioning, now, account_id),
            )
            conn.execute(
                "UPDATE operator_accounts SET status = 'STRATEGY_PENDING_CONFIRMATION', updated_at = ? "
                "WHERE id = ?", (now, account_id),
            )
            conn.execute(
                "UPDATE operator_accounts SET status = 'ACTIVE', updated_at = ? WHERE id = ?",
                (now, account_id),
            )
            row = conn.execute("SELECT * FROM operator_active_strategies WHERE id = ?", (strategy_id,)).fetchone()
            saved_pillars = conn.execute(
                "SELECT * FROM operator_content_pillars WHERE strategy_id = ? ORDER BY rowid", (strategy_id,),
            ).fetchall()
        return self._active_strategy(row, saved_pillars)

    def get_active_strategy(self, account_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM operator_active_strategies WHERE account_id = ? AND status = 'ACTIVE'",
                (account_id,),
            ).fetchone()
            if row is None:
                return None
            pillars = conn.execute(
                "SELECT * FROM operator_content_pillars WHERE account_id = ? AND strategy_id = ? "
                "AND status = 'ACTIVE' ORDER BY rowid", (account_id, row["id"]),
            ).fetchall()
        return self._active_strategy(row, pillars)

    def repair_active_strategy_experiment_plan(self, account_id: str, strategy_id: str, *,
                                               experiment_plan: dict[str, Any], reason: str,
                                               occurred_at: str) -> dict[str, Any]:
        """Audited correction for a persisted plan that differed from its confirmed UI summary."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT experiment_plan_json FROM operator_active_strategies "
                "WHERE account_id = ? AND id = ? AND status = 'ACTIVE'", (account_id, strategy_id),
            ).fetchone()
            if row is None:
                raise ValueError("ACTIVE Strategy 不存在或不属于当前账号。")
            previous = json.loads(row["experiment_plan_json"])
            conn.execute(
                "UPDATE operator_active_strategies SET experiment_plan_json = ?, updated_at = ? "
                "WHERE account_id = ? AND id = ? AND status = 'ACTIVE'",
                (json.dumps(experiment_plan, ensure_ascii=False, allow_nan=False), occurred_at,
                 account_id, strategy_id),
            )
            conn.execute(
                "INSERT INTO strategy_active_change_events "
                "(id, account_id, strategy_id, event_type, reason, occurred_at, details_json) "
                "VALUES (?, ?, ?, 'EXPERIMENT_PLAN_REPAIRED', ?, ?, ?)",
                (f"strategy-plan-repair-{uuid4().hex}", account_id, strategy_id, reason, occurred_at,
                 json.dumps({"previous": previous, "corrected": experiment_plan}, ensure_ascii=False,
                            allow_nan=False)),
            )
            updated = conn.execute("SELECT * FROM operator_active_strategies WHERE id = ?", (strategy_id,)).fetchone()
            pillars = conn.execute(
                "SELECT * FROM operator_content_pillars WHERE account_id = ? AND strategy_id = ? "
                "AND status = 'ACTIVE' ORDER BY rowid", (account_id, strategy_id),
            ).fetchall()
        return self._active_strategy(updated, pillars)

    @staticmethod
    def _topic(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["score_breakdown"] = json.loads(item.pop("score_breakdown_json"))
        item["historical_evidence"] = json.loads(item.pop("historical_evidence_json"))
        item["material_requirements"] = json.loads(item.pop("material_requirements_json"))
        return item

    @classmethod
    def _topic_batch(cls, row: sqlite3.Row, topics: list[sqlite3.Row]) -> dict[str, Any]:
        batch = dict(row)
        batch["topics"] = [cls._topic(topic) for topic in topics]
        return batch

    def get_daily_topic_batch(self, account_id: str, local_date: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            batch = conn.execute(
                "SELECT * FROM operator_topic_batches WHERE account_id = ? AND local_date = ? "
                "AND status = 'CURRENT'", (account_id, local_date),
            ).fetchone()
            if batch is None:
                return None
            topics = conn.execute(
                "SELECT t.*, p.name AS pillar_name FROM operator_topics t "
                "JOIN operator_content_pillars p ON p.id = t.pillar_id "
                "WHERE t.account_id = ? AND t.batch_id = ? "
                "ORDER BY CASE t.status WHEN 'RECOMMENDED' THEN 0 ELSE 1 END, t.score DESC, t.created_at",
                (account_id, batch["id"]),
            ).fetchall()
        return self._topic_batch(batch, topics)

    def list_recent_topics(self, account_id: str, since_date: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT t.id, t.batch_id, t.pillar_id, t.title, t.status, t.score, t.created_at, "
                "b.local_date FROM operator_topics t JOIN operator_topic_batches b ON b.id = t.batch_id "
                "WHERE t.account_id = ? AND b.local_date >= ? ORDER BY b.local_date DESC, t.created_at DESC LIMIT ?",
                (account_id, since_date, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_daily_topic_batch(self, account_id: str, *, strategy_id: str, batch_id: str,
                               local_date: str, generated_at: str, generation_mode: str,
                               topics: list[dict[str, Any]]) -> dict[str, Any]:
        if len(topics) != 3 or sum(item.get("status") == "RECOMMENDED" for item in topics) != 1:
            raise ValueError("每日选题批次必须包含 3 个候选和 1 个主推。")
        if generation_mode not in {"AI", "TEMPLATE"}:
            raise ValueError("不支持的选题生成方式。")
        with self._connect() as conn:
            account = conn.execute("SELECT status FROM operator_accounts WHERE id = ?", (account_id,)).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            if account["status"] != "ACTIVE":
                raise ValueError("尚未确认运营策略，不能生成正式选题。")
            active = conn.execute(
                "SELECT id FROM operator_active_strategies WHERE account_id = ? AND status = 'ACTIVE'",
                (account_id,),
            ).fetchone()
            if active is None or active["id"] != strategy_id:
                raise ValueError("当前 ACTIVE Strategy 已变化，请刷新后重新生成。")
            active_pillars = {row["id"] for row in conn.execute(
                "SELECT id FROM operator_content_pillars WHERE account_id = ? AND strategy_id = ? "
                "AND status = 'ACTIVE'", (account_id, strategy_id),
            ).fetchall()}
            if any(item.get("pillar_id") not in active_pillars for item in topics):
                raise ValueError("选题只能关联当前账号策略中的 ACTIVE Content Pillar。")
            selected = conn.execute(
                "SELECT 1 FROM operator_topics t JOIN operator_topic_batches b ON b.id = t.batch_id "
                "WHERE t.account_id = ? AND b.local_date = ? AND t.status = 'SELECTED' LIMIT 1",
                (account_id, local_date),
            ).fetchone()
            if selected:
                raise ValueError("今天已经选择了一个选题，不能再换一批。")
            previous = conn.execute(
                "SELECT id FROM operator_topic_batches WHERE account_id = ? AND local_date = ? "
                "AND status = 'CURRENT'", (account_id, local_date),
            ).fetchone()
            next_number = int(conn.execute(
                "SELECT COALESCE(MAX(batch_number), 0) + 1 FROM operator_topic_batches "
                "WHERE account_id = ? AND local_date = ?", (account_id, local_date),
            ).fetchone()[0])
            if previous:
                skipped = [row["id"] for row in conn.execute(
                    "SELECT id FROM operator_topics WHERE account_id = ? AND batch_id = ? "
                    "AND status IN ('CANDIDATE', 'RECOMMENDED')", (account_id, previous["id"]),
                ).fetchall()]
                conn.execute(
                    "UPDATE operator_topics SET status = 'SKIPPED' WHERE account_id = ? AND batch_id = ? "
                    "AND status IN ('CANDIDATE', 'RECOMMENDED')", (account_id, previous["id"]),
                )
                conn.execute("UPDATE operator_topic_batches SET status = 'SUPERSEDED' WHERE id = ?",
                             (previous["id"],))
                conn.execute(
                    "INSERT INTO operator_topic_events "
                    "(id, account_id, batch_id, event_type, occurred_at, details_json) "
                    "VALUES (?, ?, ?, 'BATCH_REPLACED', ?, ?)",
                    (f"topic-event-{uuid4().hex}", account_id, previous["id"], generated_at,
                     json.dumps({"skipped_topic_ids": skipped}, ensure_ascii=False)),
                )
            conn.execute(
                "INSERT INTO operator_topic_batches "
                "(id, account_id, strategy_id, local_date, batch_number, generated_at, generation_mode, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'CURRENT')",
                (batch_id, account_id, strategy_id, local_date, next_number, generated_at, generation_mode),
            )
            for item in topics:
                if item.get("strategy_id") != strategy_id or item.get("account_id") != account_id:
                    raise ValueError("选题账号或策略版本不匹配。")
                conn.execute(
                    "INSERT INTO operator_topics "
                    "(id, batch_id, account_id, strategy_id, pillar_id, title, angle, description, score, "
                    "score_breakdown_json, recommendation_reason, historical_evidence_json, experiment_question, "
                    "production_difficulty, material_requirements_json, status, similarity_score, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (item["id"], batch_id, account_id, strategy_id, item["pillar_id"], item["title"],
                     item["angle"], item["description"], item["score"],
                     json.dumps(item["score_breakdown"], ensure_ascii=False, allow_nan=False),
                     item["recommendation_reason"],
                     json.dumps(item["historical_evidence"], ensure_ascii=False, allow_nan=False),
                     item["experiment_question"], item["production_difficulty"],
                     json.dumps(item["material_requirements"], ensure_ascii=False, allow_nan=False),
                     item["status"], item["similarity_score"], generated_at),
                )
            rows = conn.execute("SELECT t.*, p.name AS pillar_name FROM operator_topics t "
                                "JOIN operator_content_pillars p ON p.id = t.pillar_id "
                                "WHERE t.account_id = ? AND t.batch_id = ? "
                                "ORDER BY CASE t.status WHEN 'RECOMMENDED' THEN 0 ELSE 1 END, t.score DESC",
                                (account_id, batch_id)).fetchall()
            batch = conn.execute("SELECT * FROM operator_topic_batches WHERE id = ?", (batch_id,)).fetchone()
        return self._topic_batch(batch, rows)

    def select_daily_topic(self, account_id: str, topic_id: str, *, local_date: str,
                           occurred_at: str) -> dict[str, Any]:
        with self._connect() as conn:
            account = conn.execute("SELECT status FROM operator_accounts WHERE id = ?", (account_id,)).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            if account["status"] != "ACTIVE":
                raise ValueError("尚未确认运营策略，不能选择正式选题。")
            row = conn.execute(
                "SELECT t.*, b.strategy_id, b.local_date, b.status AS batch_status "
                "FROM operator_topics t JOIN operator_topic_batches b ON b.id = t.batch_id "
                "WHERE t.account_id = ? AND t.id = ? AND b.local_date = ? AND b.status = 'CURRENT'",
                (account_id, topic_id, local_date),
            ).fetchone()
            if row is None:
                raise ValueError("选题不存在、已过期或不属于当前账号。")
            active = conn.execute(
                "SELECT id FROM operator_active_strategies WHERE account_id = ? AND status = 'ACTIVE'",
                (account_id,),
            ).fetchone()
            if active is None or row["strategy_id"] != active["id"]:
                raise ValueError("该选题关联的策略已不再 ACTIVE。")
            already_selected = conn.execute(
                "SELECT 1 FROM operator_topics t JOIN operator_topic_batches b ON b.id = t.batch_id "
                "WHERE t.account_id = ? AND b.local_date = ? AND t.status = 'SELECTED' LIMIT 1",
                (account_id, local_date),
            ).fetchone()
            if already_selected:
                raise ValueError("今天已经选择了一个选题。")
            if row["status"] == "SELECTED":
                raise ValueError("这个选题已经选中。")
            if row["status"] not in {"CANDIDATE", "RECOMMENDED"}:
                raise ValueError("该候选已被跳过或拒绝，不能选择。")
            conn.execute(
                "UPDATE operator_topics SET status = CASE WHEN id = ? THEN 'SELECTED' ELSE 'SKIPPED' END "
                "WHERE account_id = ? AND batch_id = ? AND status IN ('CANDIDATE', 'RECOMMENDED')",
                (topic_id, account_id, row["batch_id"]),
            )
            conn.execute(
                "INSERT INTO operator_topic_events "
                "(id, account_id, topic_id, batch_id, event_type, occurred_at, details_json) "
                "VALUES (?, ?, ?, ?, 'TOPIC_SELECTED', ?, ?)",
                (f"topic-event-{uuid4().hex}", account_id, topic_id, row["batch_id"], occurred_at,
                 json.dumps({"pillar_id": row["pillar_id"], "score": row["score"]}, ensure_ascii=False)),
            )
            topics = conn.execute("SELECT t.*, p.name AS pillar_name FROM operator_topics t "
                                  "JOIN operator_content_pillars p ON p.id = t.pillar_id "
                                  "WHERE t.account_id = ? AND t.batch_id = ? "
                                  "ORDER BY CASE t.status WHEN 'SELECTED' THEN 0 WHEN 'RECOMMENDED' THEN 1 ELSE 2 END, t.score DESC",
                                  (account_id, row["batch_id"])).fetchall()
            batch = conn.execute("SELECT * FROM operator_topic_batches WHERE id = ?", (row["batch_id"],)).fetchone()
        return self._topic_batch(batch, topics)

    @staticmethod
    def _content_draft(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["content"] = json.loads(item.pop("content_json"))
        return item

    def get_selected_topic_for_draft(self, account_id: str, topic_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            account = conn.execute(
                "SELECT id, name, platform, status FROM operator_accounts WHERE id = ?", (account_id,),
            ).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            if account["status"] != "ACTIVE":
                raise ValueError("账号策略尚未确认，不能生成正式内容草稿。")
            active = conn.execute(
                "SELECT * FROM operator_active_strategies WHERE account_id = ? AND status = 'ACTIVE'",
                (account_id,),
            ).fetchone()
            if active is None:
                raise ValueError("账号没有 ACTIVE Strategy，不能生成正式内容草稿。")
            row = conn.execute(
                "SELECT t.*, p.name AS pillar_name, p.description AS pillar_description, p.goal AS pillar_goal, "
                "b.generated_at AS topic_generated_at, "
                "b.local_date AS topic_date FROM operator_topics t "
                "JOIN operator_topic_batches b ON b.id = t.batch_id "
                "JOIN operator_content_pillars p ON p.id = t.pillar_id "
                "WHERE t.account_id = ? AND t.id = ? AND t.status = 'SELECTED' "
                "AND t.strategy_id = ? AND b.strategy_id = ?",
                (account_id, topic_id, active["id"], active["id"]),
            ).fetchone()
            if row is None:
                raise ValueError("请先在今日运营中选择此账号当前策略下的选题。")
            strategy = dict(active)
            strategy["content_pillars"] = json.loads(strategy.pop("content_pillars_json"))
            strategy["experiment_plan"] = json.loads(strategy.pop("experiment_plan_json"))
            topic = self._topic(row)
            topic["topic_generated_at"] = topic.pop("topic_generated_at")
            topic["topic_date"] = topic.pop("topic_date")
        return {"account": dict(account), "strategy": strategy, "topic": topic}

    def get_content_draft(self, account_id: str, topic_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM operator_content_drafts WHERE account_id = ? AND topic_id = ? "
                "AND status = 'CURRENT'", (account_id, topic_id),
            ).fetchone()
        return self._content_draft(row) if row else None

    def save_content_draft(self, account_id: str, topic_id: str, *, draft_id: str,
                           strategy_id: str, strategy_version: int, platform: str,
                           content: dict[str, Any], occurred_at: str) -> dict[str, Any]:
        with self._connect() as conn:
            account = conn.execute(
                "SELECT status, platform FROM operator_accounts WHERE id = ?", (account_id,),
            ).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            if account["status"] != "ACTIVE":
                raise ValueError("账号策略尚未确认，不能生成正式内容草稿。")
            active = conn.execute(
                "SELECT id, version FROM operator_active_strategies WHERE account_id = ? AND status = 'ACTIVE'",
                (account_id,),
            ).fetchone()
            if active is None or active["id"] != strategy_id or active["version"] != strategy_version:
                raise ValueError("当前 ACTIVE Strategy 已变化，请刷新选题后重试。")
            selected = conn.execute(
                "SELECT 1 FROM operator_topics WHERE account_id = ? AND id = ? AND strategy_id = ? "
                "AND status = 'SELECTED'", (account_id, topic_id, strategy_id),
            ).fetchone()
            if selected is None:
                raise ValueError("只有用户已选择的选题才能生成内容草稿。")
            if account["platform"] != platform:
                raise ValueError("草稿平台必须与业务账号平台一致。")
            previous = conn.execute(
                "SELECT id, version FROM operator_content_drafts WHERE account_id = ? AND topic_id = ? "
                "AND status = 'CURRENT'", (account_id, topic_id),
            ).fetchone()
            version = int(previous["version"]) + 1 if previous else 1
            if previous:
                conn.execute("UPDATE operator_content_drafts SET status = 'SUPERSEDED' WHERE id = ?",
                             (previous["id"],))
            conn.execute(
                "INSERT INTO operator_content_drafts "
                "(id, account_id, topic_id, strategy_id, strategy_version, version, platform, "
                "generation_mode, status, content_json, generated_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'AI', 'CURRENT', ?, ?, ?)",
                (draft_id, account_id, topic_id, strategy_id, strategy_version, version, platform,
                 json.dumps(content, ensure_ascii=False, allow_nan=False), occurred_at, occurred_at),
            )
            conn.execute(
                "INSERT INTO operator_content_draft_events "
                "(id, account_id, draft_id, topic_id, event_type, occurred_at, details_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"content-draft-event-{uuid4().hex}", account_id, draft_id, topic_id,
                 "REGENERATED" if previous else "GENERATED", occurred_at,
                 json.dumps({"version": version, "strategy_version": strategy_version}, ensure_ascii=False)),
            )
            saved = conn.execute("SELECT * FROM operator_content_drafts WHERE id = ?", (draft_id,)).fetchone()
        return self._content_draft(saved)

    def update_content_draft(self, account_id: str, topic_id: str, content: dict[str, Any], *,
                             occurred_at: str) -> dict[str, Any]:
        with self._connect() as conn:
            account = conn.execute(
                "SELECT status FROM operator_accounts WHERE id = ?", (account_id,),
            ).fetchone()
            if account is None:
                raise AccountNotFoundError(account_id)
            if account["status"] != "ACTIVE":
                raise ValueError("账号策略尚未确认，不能编辑正式内容草稿。")
            row = conn.execute(
                "SELECT d.* FROM operator_content_drafts d "
                "JOIN operator_active_strategies s ON s.id = d.strategy_id AND s.status = 'ACTIVE' "
                "JOIN operator_topics t ON t.id = d.topic_id AND t.status = 'SELECTED' "
                "WHERE d.account_id = ? AND d.topic_id = ? AND d.status = 'CURRENT' "
                "AND d.strategy_id = s.id",
                (account_id, topic_id),
            ).fetchone()
            if row is None:
                raise ValueError("当前选题没有可编辑的草稿，或其策略已不再 ACTIVE。")
            conn.execute(
                "UPDATE operator_content_drafts SET content_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(content, ensure_ascii=False, allow_nan=False), occurred_at, row["id"]),
            )
            conn.execute(
                "INSERT INTO operator_content_draft_events "
                "(id, account_id, draft_id, topic_id, event_type, occurred_at, details_json) "
                "VALUES (?, ?, ?, ?, 'EDITED', ?, ?)",
                (f"content-draft-event-{uuid4().hex}", account_id, row["id"], topic_id, occurred_at,
                 json.dumps({"version": row["version"]}, ensure_ascii=False)),
            )
            updated = conn.execute("SELECT * FROM operator_content_drafts WHERE id = ?", (row["id"],)).fetchone()
        return self._content_draft(updated)
