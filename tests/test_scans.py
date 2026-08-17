import asyncio

from maigret.result import MaigretCheckResult, MaigretCheckStatus

import app.routers.scans as scans_module
from app.main import app


async def _wait_until_done(client, scan_id, tries=50):
    for _ in range(tries):
        resp = await client.get(f"/api/scans/{scan_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["finished"]:
            return data
        await asyncio.sleep(0.05)
    raise AssertionError("scan did not finish in time")


async def fake_search(username, site_dict, logger, query_notify=None, output_container=None, **kwargs):
    query_notify.start(username, "username")
    for i, (name, site) in enumerate(site_dict.items()):
        status = MaigretCheckStatus.CLAIMED if i == 0 else MaigretCheckStatus.AVAILABLE
        result = MaigretCheckResult(
            username, name, f"https://example.com/{name}/{username}", status,
            ids_data={"username": username}, tags=["testing"],
        )
        query_notify.update(result, False)
        if output_container is not None:
            output_container[name] = {"status": result}
    query_notify.finish()


async def failing_search(*args, **kwargs):
    raise RuntimeError("boom")


async def slow_search(username, site_dict, logger, query_notify=None, output_container=None, **kwargs):
    query_notify.start(username, "username")
    await asyncio.sleep(5)
    query_notify.finish()


async def test_scan_requires_login(client):
    resp = await client.post("/scan", data={"username": "johndoe", "scope": "quick"})
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/login")


async def test_invalid_username_rejected(logged_in, monkeypatch):
    resp = await logged_in.post("/scan", data={"username": "https://evil.com", "scope": "quick"})
    assert resp.status_code == 400


async def test_scan_runs_and_completes(logged_in, monkeypatch):
    monkeypatch.setattr("app.services.scanner.search", fake_search)
    resp = await logged_in.post("/scan", data={"username": "johndoe", "scope": "quick"})
    assert resp.status_code == 303
    scan_id = int(resp.headers["location"].rstrip("/").split("/")[-1])

    data = await _wait_until_done(logged_in, scan_id)
    assert data["status"] == "done"
    assert data["found_count"] >= 1
    assert data["found"][0]["username"] == "johndoe"
    assert data["found"][0]["status"] == "Claimed"
    assert data["finished"] is True

    page = await logged_in.get(f"/scans/{scan_id}")
    assert page.status_code == 200
    assert "Found profiles" in page.text


async def test_one_scan_at_a_time(logged_in):
    app.state.current_scan = 999
    resp = await logged_in.post("/scan", data={"username": "busy", "scope": "quick"})
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/scans/999")
    app.state.current_scan = None


async def test_scan_error_recorded(logged_in, monkeypatch):
    monkeypatch.setattr("app.services.scanner.search", failing_search)
    resp = await logged_in.post("/scan", data={"username": "boomuser", "scope": "quick"})
    scan_id = int(resp.headers["location"].rstrip("/").split("/")[-1])
    data = await _wait_until_done(logged_in, scan_id)
    assert data["status"] == "error"
    assert data["error"] == "boom"


async def test_scan_not_found(logged_in):
    resp = await logged_in.get("/scans/999999")
    assert resp.status_code == 404


async def test_cancel_scan(logged_in, monkeypatch):
    monkeypatch.setattr("app.services.scanner.search", slow_search)
    resp = await logged_in.post("/scan", data={"username": "cancelme", "scope": "quick"})
    scan_id = int(resp.headers["location"].rstrip("/").split("/")[-1])
    await asyncio.sleep(0.05)

    cancel_resp = await logged_in.post(f"/scans/{scan_id}/cancel")
    assert cancel_resp.status_code == 200

    data = await _wait_until_done(logged_in, scan_id)
    assert data["status"] == "cancelled"


async def test_cancel_requires_login(client):
    resp = await client.post("/scans/1/cancel")
    assert resp.status_code == 403


async def test_cancel_when_not_running(logged_in):
    resp = await logged_in.post("/scans/999999/cancel")
    assert resp.status_code == 409


async def test_export_json_and_csv(logged_in, monkeypatch):
    monkeypatch.setattr("app.services.scanner.search", fake_search)
    resp = await logged_in.post("/scan", data={"username": "exportme", "scope": "quick"})
    scan_id = int(resp.headers["location"].rstrip("/").split("/")[-1])
    await _wait_until_done(logged_in, scan_id)

    r = await logged_in.get(f"/scans/{scan_id}/export.json")
    assert r.status_code == 200
    assert r.json()[0]["username"] == "exportme"
    assert "attachment" in r.headers["content-disposition"]

    r = await logged_in.get(f"/scans/{scan_id}/export.csv")
    assert r.status_code == 200
    assert r.text.startswith("site_name,url,tags,extracted_ids")


async def test_scan_rate_limited(logged_in, monkeypatch):
    monkeypatch.setattr(scans_module, "SCAN_RATE_LIMIT", 2)
    monkeypatch.setattr("app.services.scanner.search", fake_search)

    for i in range(2):
        resp = await logged_in.post("/scan", data={"username": f"rl{i}", "scope": "quick"})
        assert resp.status_code == 303
        scan_id = int(resp.headers["location"].rstrip("/").split("/")[-1])
        await _wait_until_done(logged_in, scan_id)
        app.state.current_scan = None

    resp = await logged_in.post("/scan", data={"username": "rl2", "scope": "quick"})
    assert resp.status_code == 429


async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}