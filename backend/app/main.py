"""FastAPI entry point. Run with: uvicorn app.main:app (from the backend folder)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__, config
from app.db import db_ok, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Fantasy Manager", version=__version__, lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    """Basic check that the backend, database and data folder are working."""
    return {
        "status": "ok",
        "version": __version__,
        "database": "ok" if db_ok() else "error",
        "data_dir": str(config.DATA_DIR),
    }
