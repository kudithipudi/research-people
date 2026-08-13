from pathlib import Path

import aiosqlite

from app.config import get_settings

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def get_db(db_path: str | None = None) -> aiosqlite.Connection:
    settings = get_settings()
    path = db_path or settings.db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db(db_path: str | None = None) -> None:
    db = await get_db(db_path)
    try:
        await db.executescript(SCHEMA_PATH.read_text())
        await db.commit()
    finally:
        await db.close()


async def mark_interrupted_scans(db_path: str | None = None) -> None:
    """Flag scans that died mid-run (worker/process restart)."""
    db = await get_db(db_path)
    try:
        await db.execute(
            "UPDATE scans SET status = 'error', error = 'interrupted by restart' "
            "WHERE status IN ('queued', 'running')"
        )
        await db.commit()
    finally:
        await db.close()