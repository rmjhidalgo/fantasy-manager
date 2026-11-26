"""Watched folder: import Yahoo pages automatically when they're saved into a folder."""

import logging
import threading
import time
from pathlib import Path

from watchfiles import Change, watch

from app.importer.service import ImportResult, import_path
from app.importer.source import SUPPORTED_EXTENSIONS

log = logging.getLogger(__name__)

_thread: threading.Thread | None = None
_stop: threading.Event | None = None
_folder: Path | None = None
recent: list[dict] = []  # latest results, newest first, shown on the Import screen


def _remember(res: ImportResult) -> None:
    recent.insert(0, res.to_dict())
    del recent[50:]


def _wait_until_written(path: Path, timeout: float = 30) -> bool:
    """Browsers write files in chunks; wait until the size stops changing."""
    last = -1
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size == last and size > 0:
            return True
        last = size
        time.sleep(0.5)
    return path.exists()


def _import_file(path: Path) -> None:
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS or not _wait_until_written(path):
        return
    try:
        res = import_path(path, source="folder")
    except Exception as e:  # keep the watcher alive whatever happens
        log.exception("Folder import failed for %s", path)
        res = ImportResult(path.name, "error", summary=f"Unexpected error: {e}")
    if res.status != "duplicate":
        _remember(res)


def _run(folder: Path, stop: threading.Event) -> None:
    # Pick up pages saved while the app wasn't running (duplicates are skipped quickly).
    for p in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime):
        if stop.is_set():
            return
        if p.is_file():
            _import_file(p)
    for changes in watch(folder, stop_event=stop, recursive=False):
        for change, name in changes:
            if change in (Change.added, Change.modified):
                _import_file(Path(name))


def start(folder: str | None) -> None:
    """Start (or restart) watching `folder`; None stops watching."""
    global _thread, _stop, _folder
    stop()
    if not folder:
        return
    path = Path(folder)
    if not path.is_dir():
        raise ValueError(f"Folder not found: {folder}")
    _stop = threading.Event()
    _folder = path
    _thread = threading.Thread(target=_run, args=(path, _stop), daemon=True, name="folder-watch")
    _thread.start()


def stop() -> None:
    global _thread, _stop, _folder
    if _stop:
        _stop.set()
    if _thread:
        _thread.join(timeout=5)
    _thread = _stop = _folder = None


def status() -> dict:
    return {"folder": str(_folder) if _folder else None, "running": bool(_thread and _thread.is_alive())}
