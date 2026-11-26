"""Housekeeping: daily database backups and the "Update available" check."""

import logging
import sqlite3
import threading
import time
from datetime import UTC, date, datetime

import httpx

from app import __version__, config

log = logging.getLogger(__name__)
KEEP_BACKUPS = 14

# ------------------------------------------------------------------ backups


def backup_now() -> str | None:
    """Copy the database to backups/fantasy_manager-YYYY-MM-DD.db (once a day), keep the last 14."""
    if not config.DB_PATH.is_file():
        return None
    config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.BACKUPS_DIR / f"fantasy_manager-{date.today().isoformat()}.db"
    if not dest.exists():
        src = sqlite3.connect(config.DB_PATH)
        try:
            out = sqlite3.connect(dest)
            with out:
                src.backup(out)  # safe copy even while the app is writing
            out.close()
        finally:
            src.close()
    old = sorted(config.BACKUPS_DIR.glob("fantasy_manager-*.db"))[:-KEEP_BACKUPS]
    for p in old:
        p.unlink(missing_ok=True)
    return str(dest)


_bg: threading.Thread | None = None
_stop = threading.Event()


def _loop() -> None:
    while not _stop.is_set():
        try:
            backup_now()
        except Exception as e:  # a failed backup must never stop the app
            log.warning("Backup failed: %s", e)
        _stop.wait(6 * 3600)


def start_background() -> None:
    global _bg
    if _bg and _bg.is_alive():
        return
    _stop.clear()
    _bg = threading.Thread(target=_loop, daemon=True, name="backups")
    _bg.start()


def stop_background() -> None:
    _stop.set()


# ------------------------------------------------------------------ update check

_cache: dict = {"at": 0.0, "latest": None}


def _parse(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


def version_info(force: bool = False) -> dict:
    """Compare this copy's version with the one published on GitHub (checked at most twice a day).
    Sends nothing about you: it's a plain download of a small public text file."""
    now = time.time()
    if force or now - _cache["at"] > 12 * 3600:
        _cache["at"] = now
        try:
            r = httpx.get(config.VERSION_URL, timeout=10, headers={"User-Agent": "fantasy-manager-update-check"})
            _cache["latest"] = r.text.strip() if r.status_code == 200 and len(r.text) < 32 else None
        except httpx.HTTPError:
            _cache["latest"] = None
    latest = _cache["latest"]
    return {
        "current": __version__,
        "latest": latest,
        "update_available": bool(latest) and _parse(latest) > _parse(__version__),
        "download_url": config.DOWNLOAD_URL,
        "checked_at": datetime.fromtimestamp(_cache["at"], UTC).replace(tzinfo=None).isoformat() + "Z" if _cache["at"] else None,
    }
