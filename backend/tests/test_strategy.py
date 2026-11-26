"""Milestone 6 tests: trades, schedule grid, player search/comparison, scouting, scoring profile (made-up data)."""

import pytest
from fastapi.testclient import TestClient
from test_moves import NOW, _history, _team_games, _yahoo, small_league  # noqa: F401  (fixture)
from test_suggest import with_matchup  # noqa: F401  (fixture)

from app import mcp_server
from app.db import SessionLocal
from app.db.models import League
from app.engine.projections import virtual_id
from app.engine.strategy import compare_players, player_search, schedule_grid, scoring_profile, scout_opponent
from app.engine.trades import analyze_trade, find_trades
from app.engine.untouchables import set_untouchables
from app.main import app


@pytest.fixture
def two_teams(with_matchup):
    with SessionLocal() as db:
        # Team 20 also has a bench center
        _yahoo(db, 302, 22, "Their Bench", "FFF", "C", slot="BN", team_id=20)
        _history(db, 22, "FFF", 12)
        _team_games(db, "FFF", ["2026-11-24", "2026-11-26", "2026-11-28"])
        db.commit()
    return NOW


def test_trade_analyzer_counts_lineup_points_after_review_period(two_teams):
    with SessionLocal() as db:
        r = analyze_trade(db, db.get(League, 1), 10, 20, give=[103], get=[301], key="A", now_utc=NOW)
    assert r["effective"] == "2026-11-25"  # 2-day review
    # Rival (25 FP, PG) plays Wed/Fri/Sun for me in an empty Util slot; Weak never started for me.
    assert r["my_team"]["gain"] > 0 and r["their_team"]["gain"] < 0
    assert r["verdict"] == "Good for you"
    assert [p["name"] for p in r["get"]] == ["Rival"] and r["get"][0]["games"] == 3


def test_uneven_trade_drops_lowest_value_player(two_teams):
    with SessionLocal() as db:
        r = analyze_trade(db, db.get(League, 1), 10, 20, give=[103], get=[301, 302], key="A", now_utc=NOW)
    # I receive 2 for 1 with no free spot: my lowest-value player not in the trade goes.
    assert len(r["my_team"]["drops"]) == 1 and r["my_team"]["drops"][0]["name"] in ("Big", "Star")
    assert r["their_team"]["drops"] == []


def test_trade_analyzer_rejects_players_not_on_rosters(two_teams):
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            analyze_trade(db, db.get(League, 1), 10, 20, give=[301], get=[103], key="A", now_utc=NOW)


def test_trade_finder_never_offers_untouchables(two_teams):
    with SessionLocal() as db:
        r = find_trades(db, db.get(League, 1), 10, "A", now_utc=NOW)
        assert isinstance(r["trades"], list)
        for t in r["trades"]:
            assert t["my_gain"] >= 3 and t["their_gain"] >= 3
        set_untouchables(db, 1, 10, {101, 102, 103})
        assert find_trades(db, db.get(League, 1), 10, "A", now_utc=NOW)["trades"] == []


def test_schedule_grid(two_teams):
    with SessionLocal() as db:
        g = schedule_grid(db, db.get(League, 1), 10, now_utc=NOW)
    assert g["columns"][0]["label"] == "Week 6" and g["columns"][0]["current"]
    aaa = next(r for r in g["teams"] if r["team"] == "AAA")
    assert aaa["games"][0] == 2 and aaa["my_players"] == ["Star"]
    ccc = next(r for r in g["teams"] if r["team"] == "CCC")
    assert ccc["back_to_backs"][0] == 2  # Tue-Wed and Fri-Sat
    assert g["my_games"][0] == 6  # Star 2 + Big 2 + Weak 2
    assert "Settings" in g["notes"][0]  # playoff weeks unknown in this made-up league


def test_player_search_and_compare(two_teams):
    with SessionLocal() as db:
        lg = db.get(League, 1)
        assert player_search(db, lg, "gem")[0]["id"] == virtual_id(12)
        assert player_search(db, lg, "sta")[0]["name"] == "Star"
        c = compare_players(db, lg, 10, [101, virtual_id(12)], now_utc=NOW)
    star, gem = c["players"]
    assert star["owner"] == "Mine" or star["owner"] == "a team"
    assert star["fpts"] == pytest.approx(30) and star["games"]["rest_of_week"] == 2
    assert star["floor"] == pytest.approx(30) and len(star["last_games"]) == 6
    assert gem["owner"] == "Not on a saved page" and gem["games"]["rest_of_week"] == 4


def test_scouting_lists_opponent(two_teams):
    with SessionLocal() as db:
        s = scout_opponent(db, db.get(League, 1), 10, now_utc=NOW)
    o = s["opponents"][0]
    assert o["team"]["id"] == 20 and {r["name"] for r in o["roster"]} == {"Rival", "Their Bench"}
    assert o["games_left"] == 4 + 3


def test_scoring_profile(two_teams):
    with SessionLocal() as db:
        p = scoring_profile(db, db.get(League, 1), 10, now_utc=NOW)
    me = next(t for t in p["teams"] if t["is_me"])
    # Only the best 2 count: this made-up league has 2 lineup slots (PG, Util)
    assert me["by_category"]["PTS"] == pytest.approx(30 + 20)
    assert p["my_rank"]["PTS"] == 1 and p["league_average"]["PTS"] == pytest.approx((50 + 37) / 2, abs=0.1)


def test_strategy_api_and_mcp_tools(two_teams, monkeypatch):
    with TestClient(app) as client:
        def fake_get(url, params=None, headers=None, timeout=None):
            return client.get(url.replace(mcp_server.API, ""), params=params, headers=headers)

        monkeypatch.setattr(mcp_server.httpx, "get", fake_get)
        for url in ("/api/teams", "/api/schedule", "/api/scouting", "/api/scoring-profile", "/api/trade/find?horizon=A"):
            assert client.get(url).status_code == 200, url
        r = client.post("/api/trade/analyze", json={"other_team": 20, "give": [103], "get": [301], "horizon": "A"})
        assert r.status_code == 200 and r.json()["yahoo_url"].endswith("/nba/1/20")
        assert client.post("/api/trade/analyze", json={"other_team": 10, "give": [103], "get": [101]}).status_code == 422

        t = mcp_server.analyze_trade(["weak"], ["rival"], "A")
        assert t["verdict"] == "Good for you" and t["me"]["points_change"] > 0
        with pytest.raises(ValueError):
            mcp_server.analyze_trade(["nobody"], ["rival"])
        assert mcp_server.compare_players(["Star", "Hidden"])["players"][1]["name"] == "Hidden Gem"
        assert "AAA" in mcp_server.get_schedule()["teams"]
        assert mcp_server.scout_opponent()["opponents"][0]["team"]["id"] == 20
        assert mcp_server.get_scoring_profile()["my_rank"]["PTS"] == 1
        assert isinstance(mcp_server.find_trades("A")["ideas"], (list, str))
