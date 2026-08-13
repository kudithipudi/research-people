from tests.conftest import logged_in  # noqa: F401  (fixtures importable for pytest)


async def test_home_open(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Research People" in resp.text
    assert "Log in to scan" in resp.text
    # scan form only visible when logged in
    assert 'name="username"' not in resp.text


async def test_login_page(client):
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert 'name="password"' in resp.text


async def test_login_wrong_password(client):
    resp = await client.post("/login", data={"password": "nope"})
    assert resp.status_code == 401
    assert "Wrong password" in resp.text


async def test_login_success_and_session(client):
    resp = await client.post("/login", data={"password": "test-pass"})
    assert resp.status_code == 303
    home = await client.get("/")
    assert home.status_code == 200
    assert 'name="username"' in home.text


async def test_logout_clears_session(client):
    await client.post("/login", data={"password": "test-pass"})
    resp = await client.post("/logout")
    assert resp.status_code == 303
    home = await client.get("/")
    assert 'name="username"' not in home.text