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


async def check_and_record_rate_limit(
    conn: aiosqlite.Connection,
    *,
    ip: str,
    route: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """Record a hit for (ip, route) and return whether it's within `limit`
    hits in the trailing `window_seconds`. Also prunes hits for this route
    older than the window, so the table doesn't grow unbounded."""
    offset = f"-{window_seconds} seconds"
    await conn.execute(
        "DELETE FROM rate_limit_hits WHERE route = ?"
        " AND created_at < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
        (route, offset),
    )
    cur = await conn.execute(
        "SELECT COUNT(*) FROM rate_limit_hits WHERE route = ? AND ip = ?"
        " AND created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
        (route, ip, offset),
    )
    row = await cur.fetchone()
    if row[0] >= limit:
        await conn.commit()
        return False
    await conn.execute(
        "INSERT INTO rate_limit_hits (ip, route) VALUES (?, ?)", (ip, route)
    )
    await conn.commit()
    return True


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