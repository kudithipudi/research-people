-- Canonical SQLite schema for research-people (WAL, foreign_keys ON set in app/db.py).

CREATE TABLE IF NOT EXISTS scans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    id_type       TEXT NOT NULL DEFAULT 'username',
    scope         TEXT NOT NULL DEFAULT 'standard',
    site_count    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued', 'running', 'done', 'error', 'cancelled')),
    found_count   INTEGER NOT NULL DEFAULT 0,
    result_json   TEXT,
    error         TEXT,
    created_at    TEXT NOT NULL,
    completed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans (created_at DESC);