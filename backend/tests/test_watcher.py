import shutil
import tempfile
import time
from pathlib import Path

from conftest import fixture

from app.importer import watcher


def _wait_for(cond, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.2)
    return False


def test_watched_folder_imports_existing_and_new_files(fresh_db):
    team = fixture("PokemonPinoys")
    settings = fixture("settings.html")
    folder = Path(tempfile.mkdtemp(prefix="fm_watch_"))
    shutil.copy2(settings, folder / settings.name)  # already there before watching starts
    watcher.recent.clear()
    try:
        watcher.start(str(folder))
        assert watcher.status()["running"]
        assert _wait_for(lambda: any(r["page_type"] == "settings" for r in watcher.recent))

        (folder / "notes.txt").write_text("ignore me")  # not a web page: ignored silently
        shutil.copy2(team, folder / team.name)  # saved while watching
        assert _wait_for(lambda: any(r["page_type"] == "team" for r in watcher.recent))
        assert all(r["status"] in ("imported", "partial") for r in watcher.recent)
    finally:
        watcher.stop()
    assert not watcher.status()["running"]


def test_missing_folder_is_rejected():
    try:
        watcher.start(r"C:\definitely\not\a\folder")
    except ValueError as e:
        assert "not found" in str(e)
    else:
        raise AssertionError("expected ValueError")
