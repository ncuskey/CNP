"""
BCSD Child Nutrition Ops Console - FastAPI application.
Loaded by uvicorn for reload support.
"""
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.database import ensure_dirs, init_db
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure DB, vault, inbox, backups exist; seed retention rules; auto-backup if needed."""
    ensure_dirs()
    init_db()
    from app.database import get_engine
    from app.evidence import seed_retention_rules
    from app.backup import create_backup, should_auto_backup
    from sqlmodel import Session
    engine = get_engine()
    with Session(engine) as db:
        seed_retention_rules(db)
    if should_auto_backup():
        try:
            create_backup()
        except Exception:
            pass  # Don't fail startup if backup fails
    yield


app = FastAPI(
    title="BCSD Child Nutrition Ops Console",
    description="Local compliance & memory system for school nutrition programs",
    lifespan=lifespan,
)


async def _debug_exception_handler(request, exc):
    """Return traceback in response to help diagnose 500 errors."""
    return PlainTextResponse(
        f"500 Internal Server Error\n\n{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
        status_code=500,
    )


app.add_exception_handler(Exception, _debug_exception_handler)

app.include_router(router)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

vault_dir = Path(__file__).parent / "vault"
if vault_dir.exists():
    app.mount("/vault", StaticFiles(directory=str(vault_dir)), name="vault")
