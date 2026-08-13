"""Trigger and run maigret username scans as background tasks.

Every maigret call lives in this module (the library seam). Scans are
I/O-bound asyncio coroutines, so awaiting ``search()`` on the main event loop
does not block other requests (single gunicorn worker).
"""
import asyncio
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from maigret import MaigretDatabase, search
from maigret.result import MaigretCheckStatus
from maigret.utils import is_plausible_username

from app.config import get_settings
from app.db import utc_now

log = logging.getLogger("research_people.scanner")

# scope name -> top-N popular sites (maigret ranks by Alexa data); full = all.
SCOPES: dict[str, int | None] = {
    "quick": 100,
    "standard": 500,
    "full": None,
}

USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,59}$")


def bundled_db_path() -> Path:
    import maigret as _mg

    return Path(_mg.__file__).resolve().parent / "resources" / "data.json"


@lru_cache(maxsize=1)
def load_database() -> MaigretDatabase:
    """The site database is ~1.4MB of JSON — parse it once per process."""
    return MaigretDatabase().load_from_path(str(bundled_db_path()))


def select_sites(scope: str) -> dict:
    """Return the {site_name: MaigretSite} slice for the requested scope."""
    db = load_database()
    kwargs: dict = {"id_type": "username", "disabled": False}
    top = SCOPES.get(scope, 500)
    if top is not None:
        kwargs["top"] = top
    return db.ranked_sites_dict(**kwargs)


def is_valid_username(username: str) -> bool:
    if not username or not isinstance(username, str):
        return False
    if not USERNAME_RE.match(username):
        return False
    try:
        return is_plausible_username(username)
    except Exception:  # noqa: BLE001 - defensive; never fail submission
        return True


class ScanNotifier:
    """Progress collector: counts processed sites, records CLAIMED profiles.

    Duck-types the notifier interface the 0.6.4 ``search()`` calls
    (start/update/finish/warning/enrich); writes nothing to stdout/stderr.
    """

    def __init__(self, state: dict):
        self.state = state

    def start(self, message=None, id_type="username"):
        self.state["status"] = "running"

    def update(self, result, is_similar=False):
        state = self.state
        seen = state.get("seen")
        if seen is None:
            seen = state["seen"] = set()
        name = getattr(result, "site_name", None)
        if name is None or name in seen:
            return
        seen.add(name)
        state["processed"] += 1
        if getattr(result, "is_found", None) and result.is_found():
            state["found"].append(result.json())

    def finish(self, message=None):
        state = self.state
        state["processed"] = max(state["processed"], state.get("total", 0))

    def warning(self, message, symbol="-", advice=None):
        pass

    def info(self, message, symbol="*"):
        pass

    def enrich(self, message, symbol="*", verbose_only=False):
        pass


async def run_scan(app, scan_id: int, username: str, scope: str) -> None:
    """Execute the maigret search and persist the outcome."""
    settings = get_settings()
    state = {"status": "running", "processed": 0, "total": 0, "found": [], "seen": set()}
    app.state.running[scan_id] = state
    db = app.state.db
    try:
        site_dict = select_sites(scope)
        state["total"] = len(site_dict)
        await db.execute(
            "UPDATE scans SET status = 'running', site_count = ? WHERE id = ?",
            (len(site_dict), scan_id),
        )
        await db.commit()

        notifier = ScanNotifier(state)
        await search(
            username,
            site_dict,
            log,
            query_notify=notifier,
            output_container={},
            no_progressbar=True,
            timeout=settings.scan_timeout,
            max_connections=settings.scan_max_connections,
            retries=settings.scan_max_retries,
            is_parsing_enabled=True,
            id_type="username",
            proxy=settings.proxy_url or None,
            tor_proxy=settings.tor_proxy_url or None,
            i2p_proxy=settings.i2p_proxy_url or None,
        )

        result_json = json.dumps(state["found"], ensure_ascii=False)
        await db.execute(
            "UPDATE scans SET status = 'done', found_count = ?, result_json = ?, "
            "completed_at = ? WHERE id = ?",
            (len(state["found"]), result_json, utc_now(), scan_id),
        )
        await db.commit()
    except asyncio.CancelledError:
        state["status"] = "cancelled"
        await _mark_failed(db, scan_id, "cancelled", "cancelled")
        raise
    except Exception as exc:  # noqa: BLE001 - the scan row must record failure
        log.exception("scan %d failed for %r", scan_id, username)
        state["status"] = "error"
        state["error"] = str(exc)
        await _mark_failed(db, scan_id, "error", str(exc))
    finally:
        app.state.running.pop(scan_id, None)
        app.state.tasks.pop(scan_id, None)
        if app.state.current_scan == scan_id:
            app.state.current_scan = None


async def _mark_failed(db, scan_id: int, status: str, error: str) -> None:
    await db.execute(
        "UPDATE scans SET status = ?, error = ?, completed_at = ? WHERE id = ?",
        (status, error, utc_now(), scan_id),
    )
    await db.commit()