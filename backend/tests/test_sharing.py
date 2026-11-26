"""Milestone 8 tests: backups, update check, the app served from one address, first-run folder setup."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app import __version__, config, maintenance
from app.db import init_db


def test_daily_backup_keeps_last_14(fresh_db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUPS_DIR", tmp_path / "backups")
    (tmp_path / "backups").mkdir()
    for i in range(20):
        (tmp_path / "backups" / f"fantasy_manager-2026-01-{i + 1:02d}.db").write_bytes(b"x")
    init_db()
    dest = maintenance.backup_now()
    files = sorted((tmp_path / "backups").glob("fantasy_manager-*.db"))
    assert dest and len(files) == maintenance.KEEP_BACKUPS and str(files[-1]) == dest
    assert files[-1].stat().st_size > 0  # a real SQLite copy


def test_update_check(monkeypatch):
    class R:
        status_code = 200
        text = "9.9.9\n"

    monkeypatch.setattr(maintenance.httpx, "get", lambda *a, **k: R())
    info = maintenance.version_info(force=True)
    assert info["current"] == __version__ and info["latest"] == "9.9.9" and info["update_available"]
    assert info["download_url"].startswith("https://github.com/")

    def offline(*a, **k):
        raise httpx.ConnectError("no internet")

    monkeypatch.setattr(maintenance.httpx, "get", offline)
    info = maintenance.version_info(force=True)
    assert info["latest"] is None and not info["update_available"]  # offline: no false alarm


def test_version_ordering():
    assert maintenance._parse("1.10.0") > maintenance._parse("1.9.3")
    assert maintenance._parse("v1.0.0") == (1, 0, 0)


def test_watch_folder_created_on_first_run(fresh_db, tmp_path):
    from app.main import app

    target = tmp_path / "Fantasy Manager pages"
    with TestClient(app) as client:
        assert client.get("/api/watch-folder").json()["suggested"].endswith("Fantasy Manager pages")
        r = client.put("/api/watch-folder", json={"folder": str(target), "create": True})
        assert r.status_code == 200 and target.is_dir() and r.json()["running"]
        client.put("/api/watch-folder", json={"folder": None})


def test_web_interface_served_from_backend():
    if not (config.FRONTEND_DIST / "index.html").is_file():
        pytest.skip("frontend not built")
    from app.main import app

    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200 and "<div id=\"root\">" in page.text
        assert client.get("/api/health").json()["version"] == __version__  # API still wins over the web pages
