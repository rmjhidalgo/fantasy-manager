"""FastAPI entry point. Run with: uvicorn app.main:app (from the backend folder)."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__, assistant, config
from app.api.assistant import router as assistant_router
from app.api.engine import router as engine_router
from app.api.imports import router as imports_router
from app.api.imports import start_saved_watcher
from app.api.moves import router as moves_router
from app.db import db_ok, init_db
from app.importer import watcher
from app.nba import sync

# Set FM_NO_BACKGROUND=1 (tests) to skip folder watching and NBA downloads on startup.
BACKGROUND = os.environ.get("FM_NO_BACKGROUND") != "1"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if BACKGROUND:
        start_saved_watcher()
        sync.start_background()  # downloads NBA data now if it's older than 3 hours, then keeps it fresh
    yield
    watcher.stop()
    sync.stop_background()


app = FastAPI(title="Fantasy Manager", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def assistant_gate(request: Request, call_next):
    """Requests from the MCP server (Claude): refused while the assistant is switched off; otherwise noted."""
    if request.headers.get(assistant.CLIENT_HEADER) == "mcp":
        if not assistant.enabled():
            return JSONResponse({"detail": "The AI assistant is switched off in Fantasy Manager (Settings tab)."}, status_code=403)
        if request.method != "GET":
            return JSONResponse({"detail": "Claude has read-only access to Fantasy Manager."}, status_code=403)
        assistant.touch()
    return await call_next(request)


app.include_router(imports_router)
app.include_router(assistant_router)
app.include_router(engine_router)
app.include_router(moves_router)


@app.get("/api/health")
def health() -> dict:
    """Basic check that the backend, database and data folder are working."""
    return {
        "status": "ok",
        "version": __version__,
        "database": "ok" if db_ok() else "error",
        "data_dir": str(config.DATA_DIR),
    }
