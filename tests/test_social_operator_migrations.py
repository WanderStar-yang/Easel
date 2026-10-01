from __future__ import annotations

import sqlite3

from easel.social_operator.repository import OperatorAccountRepository


def test_v16_database_upgrade_adds_platform_post_id_without_losing_history(tmp_path):
    path = tmp_path / "operator.sqlite3"
    repository = OperatorAccountRepository(path)
    repository.initialize()
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO historical_posts "
            "(id, account_id, platform, publish_time, title, content_source, created_at, updated_at) "
            "VALUES ('legacy-post', 'douyin-pet', 'douyin', '2026-09-01', '历史作品', 'UNKNOWN', 'now', 'now')"
        )
        conn.execute("DROP INDEX idx_operator_published_posts_platform_id")
        conn.execute("ALTER TABLE operator_published_posts DROP COLUMN platform_post_id")
        conn.execute("PRAGMA user_version = 16")

    upgraded = OperatorAccountRepository(path)
    upgraded.initialize()

    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(operator_published_posts)")}
        assert "platform_post_id" in columns
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 17
        assert conn.execute("SELECT id, title FROM historical_posts WHERE account_id='douyin-pet'").fetchall() == [
            ("legacy-post", "历史作品")
        ]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
