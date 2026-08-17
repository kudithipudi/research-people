import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "data/research_people.db"
    # e.g. "/research-people" when proxied behind a sub-path. Used only as a
    # template value (Jinja {{ prefix }} global); NEVER passed to FastAPI.
    root_path: str = ""

    # Shared password that gates triggering scans (session-cookie login).
    search_password: str = ""
    # Signs the session cookie. Set SESSION_SECRET in .env for prod so sessions
    # survive restarts; otherwise a fresh random key is generated each boot.
    session_secret: str = secrets.token_urlsafe(32)
    session_max_age_seconds: int = 8 * 3600

    # Scan tuning (passed through to maigret's search()).
    scan_timeout: float = 5.0
    scan_max_connections: int = 100
    scan_max_retries: int = 0
    # Optional proxy passthroughs for maigret (residential proxies etc).
    proxy_url: str = ""
    tor_proxy_url: str = ""
    i2p_proxy_url: str = ""

    # Per-IP rate limit on POST /scan (standards §10).
    rate_limit_per_minute: int = 20
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()