from __future__ import annotations

import os
import sqlite3
import subprocess
import sys


def test_alembic_initial_migration_creates_required_tables(tmp_path) -> None:
    database_path = tmp_path / "migration-test.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{database_path.as_posix()}",
        "APP_ENV": "test",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    required = {
        "questions",
        "answers",
        "claims",
        "claim_clusters",
        "article_drafts",
        "image_versions",
        "task_jobs",
        "task_logs",
        "publish_schedules",
        "system_settings",
        "model_usage_logs",
        "prompt_versions",
    }
    assert required.issubset(tables)

