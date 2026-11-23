import asyncio
import time
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db, get_db
from app.engine.synchronizer import LogSynchronizer
from app.engine.retention import cleanup_old_raw_events
from app.api import auth, dashboard, sessions, export, users, sync, audit

logger = logging.getLogger("uvicorn.error")


async def periodic_log_sync():
    """Background task to sync logs periodically every 15 seconds."""
    logger.info(f"[AutoSync] Background log sync loop started (interval: {settings.SYNC_INTERVAL_SECONDS}s).")
    last_retention_check: float = 0.0

    while True:
        try:
            await asyncio.sleep(settings.SYNC_INTERVAL_SECONDS)
            if settings.AUTO_SYNC_ENABLED:
                with get_db() as conn:
                    sync_engine = LogSynchronizer(conn)
                    # 1. Ingest new raw events from all log files
                    sync_stats = sync_engine.sync_all()
                    # 2. Correlate sessions
                    corr_stats = sync_engine.correlate()

                    if sync_stats.get("errors"):
                        logger.warning(f"[AutoSync] Errors/warnings during sync: {sync_stats['errors']}")

                    if sync_stats.get("events_imported", 0) > 0 or corr_stats.get("sessions_updated", 0) > 0:
                        logger.info(
                            f"[AutoSync] Imported {sync_stats.get('events_imported', 0)} events from "
                            f"{sync_stats.get('files_updated', 0)} files. Sessions updated: "
                            f"{corr_stats.get('sessions_updated', 0)} (Active now: {corr_stats.get('active_sessions', 0)})."
                        )

            # Daily Auto-Retention Cleanup (runs once every 24 hours)
            now_mono = time.monotonic()
            if now_mono - last_retention_check >= 86400:
                try:
                    await asyncio.to_thread(cleanup_old_raw_events, settings.RAW_EVENTS_RETENTION_DAYS)
                    last_retention_check = now_mono
                except Exception as ret_err:
                    logger.error(f"[Retention] Error during background raw events cleanup: {ret_err}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("[AutoSync] Background log sync loop cancelled.")
            break
        except Exception as e:
            logger.error(f"[AutoSync] Error during background log sync tick: {e}", exc_info=True)
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    init_db()

    # Initial sync on startup if log directory exists
    try:
        with get_db() as conn:
            sync_engine = LogSynchronizer(conn)
            sync_engine.sync()
    except Exception:
        pass

    # Start background auto-sync task
    sync_task = None
    if settings.AUTO_SYNC_ENABLED:
        sync_task = asyncio.create_task(periodic_log_sync())

    yield

    # Shutdown
    if sync_task:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    description="SoftEther VPN Connection History & Session Log Management Panel",
    version="1.0.0",
    lifespan=lifespan
)


# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS setup for safe origins
allowed_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(sessions.router)
app.include_router(export.router)
app.include_router(users.router)
app.include_router(sync.router)
app.include_router(audit.router)

# Mount Static Files & Frontend
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

template_file = Path(__file__).parent / "templates" / "index.html"


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main Single Page Application interface."""
    if template_file.exists():
        return FileResponse(template_file)
    return HTMLResponse("<h1>SoftEther VPN Log Panel</h1><p>Frontend template not initialized.</p>")


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health check endpoint for systemd and monitoring."""
    return {"status": "ok", "app": settings.APP_NAME, "version": "1.0.0"}
