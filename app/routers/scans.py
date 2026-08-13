import asyncio
import csv
import io
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import get_settings
from app.db import utc_now
from app.routers.auth import is_admin
from app.services import scanner

router = APIRouter()


def _login_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(f"{get_settings().root_path}/login", status_code=303)


async def _fetch_scan_row(request: Request, scan_id: int):
    db = request.app.state.db
    cur = await db.execute(
        "SELECT id, username, id_type, scope, site_count, status, found_count, "
        "result_json, error, created_at, completed_at FROM scans WHERE id = ?",
        (scan_id,),
    )
    return await cur.fetchone()


@router.post("/scan")
async def create_scan(request: Request):
    if not is_admin(request):
        return _login_redirect(request)

    form = await request.form()
    username = (form.get("username") or "").strip()
    scope = (form.get("scope") or "standard").strip()

    if not scanner.is_valid_username(username):
        raise HTTPException(status_code=400, detail="Invalid username")
    if scope not in scanner.SCOPES:
        raise HTTPException(status_code=400, detail="Invalid scope")

    current = getattr(request.app.state, "current_scan", None)
    if current is not None:
        # One scan at a time: send the operator to the live report instead.
        return RedirectResponse(
            f"{get_settings().root_path}/scans/{current}", status_code=303
        )

    site_count = len(scanner.select_sites(scope))
    db = request.app.state.db
    cur = await db.execute(
        "INSERT INTO scans (username, id_type, scope, site_count, status, created_at) "
        "VALUES (?, 'username', ?, ?, 'queued', ?)",
        (username, scope, site_count, utc_now()),
    )
    await db.commit()
    scan_id = cur.lastrowid

    request.app.state.current_scan = scan_id
    task = asyncio.create_task(scanner.run_scan(request.app, scan_id, username, scope))
    request.app.state.tasks[scan_id] = task
    return RedirectResponse(f"{get_settings().root_path}/scans/{scan_id}", status_code=303)


@router.post("/scans/{scan_id}/cancel")
async def cancel_scan(request: Request, scan_id: int):
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Login required")
    task = request.app.state.tasks.get(scan_id)
    if task is None or task.done():
        raise HTTPException(status_code=409, detail="Scan is not running")
    task.cancel()
    return {"cancelling": True}


@router.get("/scans/{scan_id}")
async def scan_page(request: Request, scan_id: int):
    row = await _fetch_scan_row(request, scan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    data = dict(row)
    finished = data["status"] in ("done", "error", "cancelled")
    live = request.app.state.running.get(scan_id)
    if live:
        data["processed"] = live["processed"]
        data["total"] = live["total"]
        data["found"] = live["found"]
    else:
        try:
            data["found"] = json.loads(data.get("result_json") or "[]")
        except json.JSONDecodeError:
            data["found"] = []
        data["processed"] = data["site_count"] if finished else 0
        data["total"] = data["site_count"]
    data["finished"] = finished
    data.pop("result_json", None)

    return request.app.state.templates.TemplateResponse(
        request, "scan.html", {"scan": data, "is_admin": is_admin(request)}
    )


@router.get("/api/scans/{scan_id}")
async def scan_api(request: Request, scan_id: int):
    row = await _fetch_scan_row(request, scan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    data = dict(row)
    live = request.app.state.running.get(scan_id)
    if live:
        data["processed"] = live["processed"]
        data["total"] = live["total"]
        data["found"] = live["found"]
        data["finished"] = False
    else:
        try:
            data["found"] = json.loads(data.get("result_json") or "[]")
        except json.JSONDecodeError:
            data["found"] = []
        data["processed"] = data["site_count"]
        data["total"] = data["site_count"]
        data["finished"] = True
    data.pop("result_json", None)
    return data


async def _scan_found(request: Request, scan_id: int):
    row = await _fetch_scan_row(request, scan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    data = dict(row)
    live = request.app.state.running.get(scan_id)
    if live:
        return data["username"], scan_id, live["found"]
    try:
        found = json.loads(data.get("result_json") or "[]")
    except json.JSONDecodeError:
        found = []
    return data["username"], scan_id, found


@router.get("/scans/{scan_id}/export.json")
async def export_json(request: Request, scan_id: int):
    username, scan_id, found = await _scan_found(request, scan_id)
    payload = json.dumps(found, ensure_ascii=False, indent=2)
    return Response(
        payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{username}-scan{scan_id}.json"'},
    )


@router.get("/scans/{scan_id}/export.csv")
async def export_csv(request: Request, scan_id: int):
    username, scan_id, found = await _scan_found(request, scan_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["site_name", "url", "tags", "extracted_ids"])
    for item in found:
        ids = item.get("ids") or {}
        writer.writerow([
            item.get("site_name", ""),
            item.get("url", ""),
            ", ".join(item.get("tags") or []),
            ", ".join(f"{k}={v}" for k, v in ids.items()),
        ])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{username}-scan{scan_id}.csv"'},
    )