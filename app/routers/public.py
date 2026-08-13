from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routers.auth import is_admin

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    templates = request.app.state.templates
    db = request.app.state.db
    recent = []
    active = None
    if db:
        cur = await db.execute(
            "SELECT id, username, scope, status, found_count, site_count, created_at "
            "FROM scans ORDER BY id DESC LIMIT 20"
        )
        recent = await cur.fetchall()
        current_scan_id = getattr(request.app.state, "current_scan", None)
        if current_scan_id:
            cur = await db.execute(
                "SELECT id, username FROM scans WHERE id = ?", (current_scan_id,)
            )
            active = await cur.fetchone()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"recent": recent, "is_admin": is_admin(request), "active": active},
    )