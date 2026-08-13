# Research People

Username dossier search inspired by and powered by [soxoj/maigret](https://github.com/soxoj/maigret)
(~2500 sites). Enter a username, choose a scan scope, and watch a live-updating
list of confirmed profiles as the scan runs in the background. Triggering a scan
requires the shared password; viewing completed reports is open.

## What it is

- Web shell around the `maigret` PyPI library (`maigret==0.6.4`, upstream
  soxoj/maigret — not the stale fork snapshot).
- Scans run as in-process background tasks (single gunicorn worker); the page
  polls `/api/scans/{id}` for live progress and streaming results.
- Results persist in SQLite; every report gets a shareable URL.
- Scope presets (Quick/Standard/Full) map to `MaigretDatabase.ranked_sites_dict(top=...)`.
- Caution: maigret sends many external requests per scan and results are
  best-effort from a datacenter IP — some sites block or CAPTCHA server IPs.
  Optional proxies via env vars pass through to maigret.

## Stack

- Python 3.12, FastAPI, aiosqlite + `db/schema.sql` (WAL, foreign_keys ON),
  pydantic-settings, Jinja2 + Tailwind (standalone CLI build) + Alpine.js,
  pytest + pytest-asyncio + httpx. Served by gunicorn behind nginx subpath
  `/research-people/`.

## Run locally

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env          # set SEARCH_PASSWORD
venv/bin/uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/. To rebuild the committed Tailwind stylesheet:

```bash
/var/www/tailwindcss \
  -i app/static/css/input.css -o app/static/css/app.css --minify
```

Run the tests (offline; the maigret search is mocked):

```bash
venv/bin/python -m pytest
```

## Deploy

- gunicorn workers=1 on `unix:/var/www/research-people/research-people.sock`
  (`gunicorn.conf.py`), systemd `research-people.service` as `www-data`.
- nginx `location /research-people/` strips the prefix
  (`rewrite ^/research-people(/.*)$ $1 break;`). The app sees bare paths; set
  `ROOT_PATH=/research-people` in `.env` purely as the `{{ prefix }}` template
  value (never passed to FastAPI).
- After changes: `sudo systemctl restart research-people` and verify
  `curl -s -o /dev/null -w '%{http_code}' https://lab.kudithipudi.org/research-people/`.

## Env vars

| Variable | Default | Meaning |
|---|---|---|
| `SEARCH_PASSWORD` | — | Shared password required to trigger scans |
| `SESSION_SECRET` | random per boot | Cookie signing key; set a stable value in prod |
| `ROOT_PATH` | `""` | Public subpath prefix for templates (e.g. `/research-people`) |
| `DB_PATH` | `data/research_people.db` | SQLite file |
| `SCAN_TIMEOUT` | `5` | Per-site timeout in seconds |
| `SCAN_MAX_CONNECTIONS` | `100` | Concurrent site checks |
| `SCAN_MAX_RETRIES` | `0` | Retry attempts per scan |
| `PROXY_URL` / `TOR_PROXY_URL` / `I2P_PROXY_URL` | `""` | Optional proxy passthrough to maigret |