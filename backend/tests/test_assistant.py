"""Milestone 5 tests: move log, AI assistant switch/install, and the MCP server tools."""

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_moves import NOW, small_league  # noqa: F401  (fixture)

from app import assistant, mcp_server
from app.db import SessionLocal
from app.db.models import League, MoveLog, Ownership, RosterSlot, Transaction
from app.engine.movelog import log_move, resolve
from app.main import app

LATER = NOW + timedelta(hours=3)


# ---------------------------------------------------------------- move log

def _log(db, name="Streamer", yahoo_id=201):
    return log_move(db, db.get(League, 1), 10, source="suggested", add_name=name, add_yahoo_id=yahoo_id,
                    drop_name="Weak", drop_yahoo_id=103, gain=12.3, horizon="A", now=NOW)


def test_move_done_when_player_on_saved_roster(small_league):
    with SessionLocal() as db:
        m = _log(db)
        db.add(RosterSlot(league_id=1, team_id=10, player_id=201, slot="BN", as_of=LATER))
        db.commit()
        resolve(db, db.get(League, 1), 10, now=LATER)
        assert db.get(MoveLog, m.id).status == "done"


def test_move_done_from_my_transaction(small_league):
    with SessionLocal() as db:
        m = _log(db)
        # 00:30 JST on Nov 24 = 15:30 UTC Nov 23, after the move was logged at 14:00 UTC
        db.add(Transaction(league_id=1, team_name="Mine", when_text="Nov 24, 12:30 am",
                           description="Streamer CCC - C Free Agent Weak BBB - C To Waivers", as_of=LATER))
        db.commit()
        resolve(db, db.get(League, 1), 10, now=LATER)
        assert db.get(MoveLog, m.id).status == "done"


def test_move_missed_when_another_team_got_him(small_league):
    with SessionLocal() as db:
        m = _log(db)
        o = db.get(Ownership, (1, 201))
        o.kind, o.team_id, o.as_of = "team", 20, LATER
        db.commit()
        resolve(db, db.get(League, 1), 10, now=LATER)
        row = db.get(MoveLog, m.id)
        assert row.status == "missed" and "another team" in row.note


def test_move_not_done_after_a_day(small_league):
    with SessionLocal() as db:
        m = _log(db)
        for r in db.query(RosterSlot).filter_by(team_id=10):
            r.as_of = NOW + timedelta(days=2)
        db.commit()
        resolve(db, db.get(League, 1), 10, now=NOW + timedelta(days=2))
        assert db.get(MoveLog, m.id).status == "not done"


def test_same_move_logged_twice_is_one_entry(small_league):
    with SessionLocal() as db:
        a = _log(db)
        b = _log(db)
        assert a.id == b.id and db.query(MoveLog).count() == 1


def test_move_log_api(small_league):
    with TestClient(app) as client:
        r = client.post("/api/move-log", json={"source": "streaming", "add_name": "Streamer", "add_yahoo_id": 201})
        assert r.status_code == 200
        log = client.get("/api/move-log").json()
        assert log["moves"][0]["add_name"] == "Streamer" and log["moves"][0]["status"] == "open"
        assert client.put(f"/api/move-log/{log['moves'][0]['id']}", json={"status": "dismissed"}).status_code == 200
        assert client.get("/api/move-log").json()["moves"][0]["status"] == "dismissed"
        assert client.post("/api/move-log", json={"source": "hack", "add_name": "x"}).status_code == 422


# ---------------------------------------------------------------- assistant switch + install

def test_mcp_requests_gated_by_switch(small_league):
    with TestClient(app) as client:
        h = {"x-fm-client": "mcp"}
        assert client.get("/api/alerts", headers=h).status_code == 200
        assert client.get("/api/assistant").json()["last_used"] is not None
        assert client.post("/api/move-log", headers=h, json={"source": "streaming", "add_name": "X"}).status_code == 403
        client.put("/api/assistant", json={"enabled": False})
        r = client.get("/api/alerts", headers=h)
        assert r.status_code == 403 and "switched off" in r.json()["detail"]
        assert client.get("/api/alerts").status_code == 200  # the app itself is unaffected
        client.put("/api/assistant", json={"enabled": True})


def test_install_keeps_other_settings_and_backs_up(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "preferences": {"theme": "dark"}}), encoding="utf-8")
    assert not assistant.installed(cfg)
    assistant.install(cfg)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["preferences"] == {"theme": "dark"} and "other" in data["mcpServers"]
    entry = data["mcpServers"]["fantasy-manager"]
    assert entry["args"] == ["-m", "app.mcp_server"] and entry["env"]["PYTHONPATH"].endswith("backend")
    assert (tmp_path / "claude_desktop_config.json.fantasy-manager.bak").is_file()
    assert assistant.installed(cfg)
    assistant.uninstall(cfg)
    assert not assistant.installed(cfg) and "other" in json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]


def test_install_without_config_explains(monkeypatch):
    monkeypatch.setattr(assistant, "find_config", lambda: None)
    with pytest.raises(FileNotFoundError):
        assistant.install()


# ---------------------------------------------------------------- MCP tools

@pytest.fixture
def mcp_client(small_league, monkeypatch):
    with TestClient(app) as client:
        def fake_get(url, params=None, headers=None, timeout=None):
            return client.get(url.replace(mcp_server.API, ""), params=params, headers=headers)

        monkeypatch.setattr(mcp_server.httpx, "get", fake_get)
        yield client


def test_mcp_tools_are_read_only_and_listed():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"get_roster", "get_matchup", "get_suggested_moves", "search_free_agents", "get_alerts", "get_data_freshness"} <= names
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_mcp_tools_return_app_numbers(mcp_client):
    fa = mcp_server.search_free_agents(window="7", limit=5)["players"]
    api = mcp_client.get("/api/free-agents", params={"window": "7"}).json()["players"]
    assert fa[0]["name"] == api[0]["name"] and fa[0]["gain_points"] == api[0]["gain"]
    assert [r["name"] for r in mcp_server.get_roster()["players"]] == ["Star", "Big", "Weak"]
    s = mcp_server.get_suggested_moves("A")
    assert s["horizon"].startswith("A") and s["adds_budget"] == 3
    assert mcp_server.list_teams()["teams"][0]["id"] == 1
    assert isinstance(mcp_server.get_alerts()["alerts"], list)
    assert mcp_server.get_matchup()["matchup"] is None  # no matchup imported in this made-up league


def test_mcp_explains_when_app_is_off(monkeypatch):
    import httpx

    def refuse(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(mcp_server.httpx, "get", refuse)
    with pytest.raises(mcp_server.AppNotRunning, match="start.bat"):
        mcp_server.list_teams()
