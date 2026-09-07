"""Foreground runtime owned by RunDock; starting it never starts production."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from backend.app.core.config import REPOSITORY_ROOT, Settings


def migrate_database(settings: Settings) -> None:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, ":memory:"):
        path = Path(url.database).resolve()
        if path.is_file():
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source:
                table = source.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchone()
                current = source.execute("SELECT version_num FROM alembic_version").fetchone() if table else None
                head = ScriptDirectory.from_config(config).get_current_head()
                if current and current[0] == head:
                    return
                backup_dir = path.parent / "backups"
                backup_dir.mkdir(exist_ok=True)
                backup = backup_dir / f"{path.name}-before-migration-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
                with sqlite3.connect(backup) as target:
                    source.backup(target)
                    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise RuntimeError("迁移前数据库备份校验失败")
    command.upgrade(config, "head")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default=str(REPOSITORY_ROOT))
    parser.add_argument("--port", type=int, default=None)
    arguments = parser.parse_args()
    if Path(arguments.app_dir).resolve() != REPOSITORY_ROOT.resolve():
        parser.error("运行目录必须是当前知乎工作台仓库")
    os.chdir(REPOSITORY_ROOT)
    os.environ.setdefault("QUEUE_BACKEND", "memory")
    os.environ.setdefault("APP_PORT", "8002")
    if arguments.port is not None:
        os.environ["APP_PORT"] = str(arguments.port)
    settings = Settings()
    migrate_database(settings)
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=settings.app_port)


if __name__ == "__main__":
    main()
