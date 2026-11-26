"""The optional AI assistant: Claude Desktop (or Claude Code) talking to this app through the local MCP server.

The MCP server (app/mcp_server.py) is started by Claude Desktop itself and reads the
app's numbers from this backend over http://127.0.0.1. This module holds the app side:
- the on/off switch (requests from the MCP server are refused while it's off)
- when Claude last asked something (the "connection light")
- installing the server entry into Claude Desktop's config file (with a backup)
"""

import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.db import SessionLocal
from app.db.models import AppSetting

SERVER_NAME = "fantasy-manager"
BACKEND_DIR = Path(__file__).resolve().parents[1]
CLIENT_HEADER = "x-fm-client"  # the MCP server sends "mcp"

_last_used: datetime | None = None


def _get(key: str) -> str | None:
    with SessionLocal() as db:
        row = db.get(AppSetting, key)
        return row.value if row else None


def _set(key: str, value: str) -> None:
    with SessionLocal() as db:
        row = db.get(AppSetting, key) or AppSetting(key=key)
        row.value = value
        db.add(row)
        db.commit()


def enabled() -> bool:
    return _get("assistant_enabled") != "0"


def set_enabled(on: bool) -> None:
    _set("assistant_enabled", "1" if on else "0")


def touch() -> None:
    """Record that Claude just used the app (kept in memory; saved at most once a minute)."""
    global _last_used
    now = datetime.now(UTC).replace(tzinfo=None)
    if _last_used is None or (now - _last_used).total_seconds() > 60:
        _set("assistant_last_used", now.isoformat())
    _last_used = now


def last_used() -> datetime | None:
    if _last_used:
        return _last_used
    v = _get("assistant_last_used")
    return datetime.fromisoformat(v) if v else None


def python_exe() -> str:
    """The Python of the app's own virtual environment (it has the MCP package installed)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        exe = exe.with_name("python.exe")
    return str(exe)


def server_entry() -> dict:
    return {
        "command": python_exe(),
        "args": ["-m", "app.mcp_server"],
        "env": {"PYTHONPATH": str(BACKEND_DIR), "FM_API": "http://127.0.0.1:8000"},
    }


def config_candidates() -> list[Path]:
    """Where Claude Desktop keeps claude_desktop_config.json on Windows (it varies by install type)."""
    out: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    roaming = os.environ.get("APPDATA")
    if local:
        data = Path(local) / "Claude-Data"
        if data.is_dir():
            out += sorted(data.glob("*/claude_desktop_config.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        pkgs = Path(local) / "Packages"
        if pkgs.is_dir():
            out += sorted(pkgs.glob("Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json"))
    if roaming:
        out.append(Path(roaming) / "Claude" / "claude_desktop_config.json")
    home = Path.home()
    out.append(home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")  # macOS
    return out


def find_config() -> Path | None:
    return next((p for p in config_candidates() if p.is_file()), None)


def _entry_in(path: Path | None) -> dict | None:
    if not path:
        return None
    try:
        return (json.loads(path.read_text(encoding="utf-8")).get("mcpServers") or {}).get(SERVER_NAME)
    except (OSError, ValueError):
        return None


def installed(path: Path | None = None) -> bool:
    return _entry_in(path or find_config()) is not None


def outdated(path: Path | None = None) -> bool:
    """Installed, but pointing at another copy of the app (e.g. after unzipping a new version)."""
    entry = _entry_in(path or find_config())
    return entry is not None and entry != server_entry()


def install(path: Path | None = None) -> dict:
    """Add (or update) this app's MCP server in Claude Desktop's config. A backup is kept next to it."""
    path = path or find_config()
    if path is None:
        raise FileNotFoundError("Claude Desktop's settings file wasn't found. Open Claude Desktop once, or add the server by hand.")
    text = path.read_text(encoding="utf-8")
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("Claude Desktop's settings file has an unexpected format; add the server by hand.")
    backup = path.with_name(path.name + ".fantasy-manager.bak")
    shutil.copy2(path, backup)
    data.setdefault("mcpServers", {})[SERVER_NAME] = server_entry()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return {"path": str(path), "backup": str(backup)}


def uninstall(path: Path | None = None) -> dict:
    path = path or find_config()
    if path is None or not installed(path):
        return {"path": str(path) if path else None, "removed": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    shutil.copy2(path, path.with_name(path.name + ".fantasy-manager.bak"))
    data["mcpServers"].pop(SERVER_NAME, None)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return {"path": str(path), "removed": True}


def claude_code_command() -> str:
    e = server_entry()
    return (f'claude mcp add {SERVER_NAME} -e PYTHONPATH="{e["env"]["PYTHONPATH"]}" '
            f'-e FM_API={e["env"]["FM_API"]} -- "{e["command"]}" -m app.mcp_server')


def status() -> dict:
    cfg = find_config()
    lu = last_used()
    return {
        "enabled": enabled(),
        "last_used": lu.isoformat() + "Z" if lu else None,
        "config_path": str(cfg) if cfg else None,
        "installed": installed(cfg),
        "outdated": outdated(cfg),
        "server_entry": {SERVER_NAME: server_entry()},
        "claude_code_command": claude_code_command(),
    }
