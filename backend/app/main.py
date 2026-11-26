"""FastAPI entry point. Run with: uvicorn app.main:app (from the backend folder)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__, config
from app.api.imports import router as imports_router
from app.api.imports import start_saved_watcher
from app.db import db_ok, init_db
from app.importer import watcher


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    start_saved_watcher()
    yield
    watcher.stop()


app = FastAPI(title="Fantasy Manager", version=__version__, lifespan=lifespan)
app.include_router(imports_router)


@app.get("/api/health")
def health() -> dict:
    """Basic check that the backend, database and data folder are working."""
    return {
        "status": "ok",
        "version": __version__,
        "database": "ok" if db_ok() else "error",
        "data_dir": str(config.DATA_DIR),
    }
