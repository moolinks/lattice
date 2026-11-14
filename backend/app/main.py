from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, LOGS_DIR, VERSION, load_settings
from .db import init_db, session_scope
from .routers import drafts, experiments, feed, ideas, inbox, links, papers, search, system
from .services.feed import refresh_if_stale
from .services.watcher import watcher

logger = logging.getLogger("lattice")


def setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = TimedRotatingFileHandler(
        LOGS_DIR / "app.log", when="midnight", backupCount=7, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(console)


def _start_scheduler() -> BackgroundScheduler | None:
    if os.environ.get("RESEARCH_HUB_SCHEDULER", "1") == "0":
        return None
    settings = load_settings()
    if not settings.get("daily_feed_enabled", True):
        return None
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    def daily_feed() -> None:
        try:
            with session_scope() as session:
                report = refresh_if_stale(session, hours=12)
            if report:
                logger.info("scheduled feed refresh: %s", report)
        except Exception:
            logger.exception("scheduled feed refresh failed")

    scheduler.add_job(
        daily_feed,
        "cron",
        hour=int(settings.get("daily_feed_hour", 8)),
        minute=10,
        id="daily-feed",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    logger.info("%s %s starting", APP_NAME, VERSION)
    if os.environ.get("RESEARCH_HUB_WATCHER", "1") != "0":
        watcher.start()
    scheduler = _start_scheduler()
    try:
        yield
    finally:
        watcher.stop()
        if scheduler:
            scheduler.shutdown(wait=False)
        logger.info("%s stopping", APP_NAME)


app = FastAPI(
    title=f"{APP_NAME} Research Hub",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(system.router)
api.include_router(papers.router)
api.include_router(ideas.router)
api.include_router(experiments.router)
api.include_router(experiments.runs_router)
api.include_router(drafts.router)
api.include_router(search.router)
api.include_router(feed.router)
api.include_router(inbox.router)
api.include_router(links.router)
app.include_router(api)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"internal error: {exc}"})


static_dir = Path(__file__).parent / "static"
assets_dir = static_dir / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith(("api/", "api")) or full_path in {"docs", "redoc", "openapi.json"}:
        raise HTTPException(404, "not found")
    if not static_dir.exists():
        return JSONResponse(
            {
                "app": APP_NAME,
                "message": "前端尚未构建。请在 frontend 目录运行 pnpm build，或用 pnpm dev 启动 5173。",
                "api": "/api/docs",
            }
        )
    candidate = (static_dir / full_path).resolve()
    try:
        candidate.relative_to(static_dir.resolve())
    except ValueError:
        raise HTTPException(404, "not found") from None
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(404, "frontend build missing")
