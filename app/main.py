import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import get_db, init_db, mark_interrupted_scans
from app.routers import auth, public, scans

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("Initializing database")
    await init_db()
    await mark_interrupted_scans()
    app.state.db = await get_db()
    app.state.running = {}
    app.state.tasks = {}
    app.state.current_scan = None
    log.info("Startup complete")
    yield
    if hasattr(app.state, "db"):
        await app.state.db.close()
        log.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Research People", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="research_people_session",
        max_age=settings.session_max_age_seconds,
        same_site="lax",
        https_only=bool(settings.root_path),
    )

    templates = Jinja2Templates(directory="app/templates")
    templates.env.globals["prefix"] = settings.root_path
    templates.env.globals["app_name"] = "Research People"
    app.state.templates = templates
    app.state.settings = settings
    app.state.running = {}
    app.state.tasks = {}
    app.state.current_scan = None

    # NOTE: mount /static bare. nginx strips the /research-people prefix before
    # proxying, so the app only ever sees unprefixed paths; setting FastAPI
    # root_path would make this mount 404 (see standards §1).
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(public.router)
    app.include_router(auth.router)
    app.include_router(scans.router)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    return app


app = create_app()