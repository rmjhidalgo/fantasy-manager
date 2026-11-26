"""Milestone 4 tests: Suggested Moves (made-up data from test_moves.small_league)."""

import json
from datetime import date

import pytest
from test_moves import NOW, _history, _team_games, _yahoo, small_league  # noqa: F401  (fixture)

from app.db import SessionLocal
from app.db.models import AppSetting, League, Matchup, Player
from app.engine.projections import Projection
from app.engine.suggest import adjust_for_horizon, suggest_moves
from app.engine.untouchables import set_untouchables
from app.engine.weeks import playoff_weeks, weeks_after


@pytest.fixture
def with_matchup(small_league):
    with SessionLocal() as db:
        # Opponent (team 20) with one steady player; I'm 10 points behind on Monday morning.
        _yahoo(db, 301, 21, "Rival", "EEE", "PG", slot="PG", team_id=20)
        _history(db, 21, "EEE", 25)
        _team_games(db, "EEE", ["2026-11-23", "2026-11-25", "2026-11-27", "2026-11-29"])
        for me, opp, s, o in ((10, 20, 90.0, 100.0), (20, 10, 100.0, 90.0)):
            db.add(Matchup(league_id=1, week=6, team_id=me, opp_team_id=opp, score=s, opp_score=o,
                           start_date="2026-11-23", end_date="2026-11-29", as_of=NOW))
        db.commit()
    return NOW


def test_playoff_weeks_counted_back_from_end_date():
    lg = League(id=1, settings_json=json.dumps({
        "playoff_weeks": [20, 21, 22], "raw": {"Playoffs": "8 teams - Week 20, 21 and 22 (ends Sunday, Apr 4)"}}))
    weeks = playoff_weeks(lg, date(2026, 11, 26))
    assert [(w, s.isoformat(), e.isoformat()) for w, s, e in weeks] == [
        (20, "2027-03-15", "2027-03-21"), (21, "2027-03-22", "2027-03-28"), (22, "2027-03-29", "2027-04-04")]
    assert weeks_after(6, date(2026, 11, 29), 2)[1] == (8, date(2026, 12, 7), date(2026, 12, 13))


def test_this_week_suggests_streamer_and_improves_win_chance(with_matchup):
    with SessionLocal() as db:
        r = suggest_moves(db, db.get(League, 1), 10, "A", now_utc=NOW)
    assert r["budget"] == 3 and r["moves"]
    first = r["moves"][0]
    assert first["add"]["name"] == "Streamer" and first["drop"]["name"] == "Weak"
    assert first["type"] == "add/drop" and first["games"] == 4
    assert any("empty lineup slot on 4" in x for x in first["reasons"])
    assert r["win_after"] > r["win_before"]
    assert r["with_moves"] > r["baseline"]


def test_untouchable_is_never_dropped(with_matchup):
    with SessionLocal() as db:
        set_untouchables(db, 1, 10, {103})
        r = suggest_moves(db, db.get(League, 1), 10, "A", now_utc=NOW)
    # Weak is protected; Big and Star are better per game than any pickup, so: Hold.
    assert r["moves"] == []
    assert {d["id"] for d in r["drop_candidates"]}.isdisjoint({103})


def test_no_adds_left_means_hold(with_matchup):
    with SessionLocal() as db:
        db.add(AppSetting(key="adds_used:1:6", value="3"))
        db.commit()
        r = suggest_moves(db, db.get(League, 1), 10, "A", now_utc=NOW)
    assert r["budget"] == 0 and r["moves"] == []


def test_open_roster_spot_needs_no_drop(with_matchup):
    with SessionLocal() as db:
        lg = db.get(League, 1)
        s = json.loads(lg.settings_json)
        s["roster_positions"] = ["PG", "Util", "BN", "BN", "IL"]  # 4 regular spots, 3 players
        lg.settings_json = json.dumps(s)
        db.commit()
        r = suggest_moves(db, lg, 10, "A", now_utc=NOW)
    assert r["moves"][0]["drop"] is None and r["moves"][0]["type"] == "add"


def test_il_move_opens_a_spot(with_matchup):
    with SessionLocal() as db:
        db.get(Player, 103).status = "O"  # Weak is out and the IL slot is free
        db.commit()
        r = suggest_moves(db, db.get(League, 1), 10, "A", now_utc=NOW)
    assert [m["name"] for m in r["il_moves"]] == ["Weak"]
    assert r["moves"][0]["drop"] is None  # the IL move makes room: no drop needed


def test_far_horizons_assume_injuries_heal():
    base = dict(yahoo_id=1, name="X", nba_team="AAA", positions=["PG"], sd=5, games_used=10, source="nba")
    proj = {
        1: Projection(status="O", fpts=30, play_prob=0.0, window_fp={"S": 20}, **base),
        2: Projection(status="OFS", fpts=30, play_prob=0.0, window_fp={"S": 30}, **{**base, "yahoo_id": 2}),
    }
    d = dict(proj)
    adjust_for_horizon(d, "D")
    assert d[1].play_prob == 0.9 and d[1].fpts == 25  # back by the playoffs; half season-long form
    assert d[2].play_prob == 0.0
    c = dict(proj)
    adjust_for_horizon(c, "C")
    assert c[1].play_prob == 0.6 and c[1].fpts == 30
    a = dict(proj)
    adjust_for_horizon(a, "A")
    assert a[1].play_prob == 0.0


def test_suggestion_api(with_matchup):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        for h in "ABCD":
            r = client.get("/api/suggestions", params={"horizon": h})
            assert r.status_code == 200, r.text
        assert client.get("/api/suggestions", params={"horizon": "E"}).status_code == 422
        assert client.put("/api/untouchables", json={"player_ids": [101, 102]}).json() == {"player_ids": [101, 102]}
        assert client.get("/api/untouchables").json() == {"player_ids": [101, 102]}
        a = client.get("/api/suggestions", params={"horizon": "A"}).json()
        assert a["moves"][0]["yahoo_url"].endswith("apid=201")
