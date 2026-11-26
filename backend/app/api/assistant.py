"""API: AI assistant settings (on/off, connection light, install into Claude Desktop)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import assistant

router = APIRouter(prefix="/api/assistant")


@router.get("")
def get_status() -> dict:
    return assistant.status()


class EnabledBody(BaseModel):
    enabled: bool


@router.put("")
def put_enabled(body: EnabledBody) -> dict:
    assistant.set_enabled(body.enabled)
    return assistant.status()


@router.post("/install")
def install() -> dict:
    try:
        result = assistant.install()
    except (FileNotFoundError, ValueError, OSError) as e:
        raise HTTPException(409, str(e)) from e
    return {**assistant.status(), "result": result}


@router.post("/uninstall")
def uninstall() -> dict:
    try:
        result = assistant.uninstall()
    except (ValueError, OSError) as e:
        raise HTTPException(409, str(e)) from e
    return {**assistant.status(), "result": result}
