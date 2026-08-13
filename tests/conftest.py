import os

os.environ.setdefault("SEARCH_PASSWORD", "test-pass")
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("ROOT_PATH", "")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.db import get_db, init_db
from app.main import app


@pytest_asyncio.fixture
async def db(tmp_path):
    settings = get_settings()
    settings.db_path = str(tmp_path / "test.db")
    await init_db(settings.db_path)
    conn = await get_db(settings.db_path)
    app.state.db = conn
    app.state.current_scan = None
    app.state.running = {}
    yield conn
    await conn.close()


@pytest_asyncio.fixture
async def client(db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def logged_in(client):
    resp = await client.post("/login", data={"password": "test-pass"})
    assert resp.status_code == 303
    return client