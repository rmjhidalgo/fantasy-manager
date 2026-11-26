"""Milestone 7 tests: playoff odds, daily summary, projection tuning, move results, re-reading saved pages."""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_moves import NOW, _history, _team_games, _yahoo, small_league  # noqa: F401  (fixture)
from test_suggest import with_matchup  # noqa: F401  (fixture)

from app import mcp_server
from app.db import SessionLocal
from app.db.models import AppSetting, FantasyTeam, GameLog, League, Matchup, MoveLog, ScheduleWeek
from app.engine.movelog import performance
from app.engine.playoffs import playoff_odds
from app.engine.projections import load_windows, project_players
from app.engine.summary import build_summary
from app.engine.tuning import apply_weights, backtest
from app.main import app


@pytest.fixture
def season(with_matchup):
    """4 teams; playoffs (top 2) in weeks 9-10, i.e. weeks 7-8 left after this one."""
    with SessionLocal() as db:
        lg = db.get(League, 1)
        s = json.loads(lg.settings_json)
        s["playoff_weeks"] = [9, 10]
        s["raw"]["Playoffs"] = "2 teams - Week 9 and 10 (ends Sunday, Dec 27)"
        lg.settings_json = json.dumps(s)
        for tid, name, w, l, pf in ((10, "Mine", 3, 2, 500.0), (20, "Rival team", 2, 3, 480.0),
                                    (30, "Strong", 5, 0, 700.0), (40, "Weak team", 0, 5, 300.0)):
            db.merge(FantasyTeam(league_id=1, team_id=tid, name=name, wins=w, losses=l, ties=0, points_for=pf, rank=1))
        _yahoo(db, 401, 31, "Superstar", "GGG", "PG", kind="team", team_id=30)
        _yahoo(db, 402, 32, "Scrub", "HHH", "PG", kind="team", team_id=40)
        _history(db, 31, "GGG", 60)
        _history(db, 32, "HHH", 5)
        days = [(datetime(2026, 11, 23) + timedelta(days=i)).date().isoformat() for i in range(35)]
        _team_games(db, "GGG", days[::2])
        _team_games(db, "HHH", days[::2])
        for team in ("AAA", "BBB", "EEE"):
            _team_games(db, team, [d for d in days[7::3]])
        for a, b, sa, sb in ((30, 40, 300.0, 20.0),):
            db.add(Matchup(league_id=1, week=6, team_id=a, opp_team_id=b, score=sa, opp_score=sb,
                           start_date="2026-11-23", end_date="2026-11-29", as_of=NOW))
            db.add(Matchup(league_id=1, week=6, team_id=b, opp_team_id=a, score=sb, opp_score=sa,
                           start_date="2026-11-23", end_date="2026-11-29", as_of=NOW))
        db.commit()
    return NOW


def test_playoff_odds_order_and_what_if(season):
    with SessionLocal() as db:
        r = playoff_odds(db, db.get(League, 1), 10, now_utc=NOW)
    assert r["playoff_spots"] == 2 and r["weeks_left"] == 2
    odds = {t["name"]: t["playoff_odds"] for t in r["teams"]}
    assert odds["Strong"] > 0.95 and odds["Weak team"] < 0.05
    assert abs(sum(odds.values()) - 2) < 1e-6  # exactly 2 teams make it in every simulated season
    wi = r["what_if"]
    assert wi["win_this_week"] >= wi["lose_this_week"]
    assert any("random" in n for n in r["notes"])


def test_playoff_odds_use_the_saved_schedule(season):
    with SessionLocal() as db:
        # Weeks 7-8: Mine plays Weak team twice; Strong plays Rival team twice
        for w in (7, 8):
            for a, b in ((10, 40), (30, 20)):
                db.add(ScheduleWeek(league_id=1, week=w, team_id=a, opp_team_id=b, as_of=NOW))
                db.add(ScheduleWeek(league_id=1, week=w, team_id=b, opp_team_id=a, as_of=NOW))
        db.commit()
        r = playoff_odds(db, db.get(League, 1), 10, now_utc=NOW)
    assert r["notes"] == ["Uses the league's real schedule for every remaining week."]
    me = next(t for t in r["teams"] if t["is_me"])
    # Facing the weakest team twice: about 2 more wins than this week's result alone
    assert me["proj_wins"] >= 3 + 2 - 0.2


def test_partial_schedule_counts_unknown_teams(season):
    with SessionLocal() as db:
        db.add(ScheduleWeek(league_id=1, week=7, team_id=10, opp_team_id=40, as_of=NOW))
        db.add(ScheduleWeek(league_id=1, week=7, team_id=40, opp_team_id=10, as_of=NOW))
        db.commit()
        r = playoff_odds(db, db.get(League, 1), 10, now_utc=NOW)
    assert any("6 of 8 remaining team-weeks" in n for n in r["notes"])


def test_import_checklist(season):
    with TestClient(app) as client:
        c = client.get("/api/import/checklist").json()
    keys = [i["key"] for i in c["setup"]] + [i["key"] for i in c["regular"]]
    assert keys == ["settings", "schedule", "my_team", "matchup", "league_home", "available", "taken"]
    sched = c["setup"][1]
    assert sched["status"] == "missing" and sched["teams_total"] == 4


def test_summary_lists_matchup_moves_and_odds(season):
    with SessionLocal() as db:
        s = build_summary(db, db.get(League, 1), 10, lineup_today=None, now_utc=NOW)
    kinds = [i["kind"] for i in s["items"]]
    assert "matchup" in kinds and "playoffs" in kinds and "moves" in kinds
    assert s["settings"]["time"] == "07:00"


def test_tuning_finds_recent_form_when_it_predicts_better(small_league):
    with SessionLocal() as db:
        # Player whose scoring jumped: 10 FP for 20 games, then 40 FP - recent form predicts better
        for i in range(30):
            d = (datetime(2026, 10, 20) + timedelta(days=i)).date().isoformat()
            db.add(GameLog(player_id=77, game_id=f"t{i}", date_et=d, team="ZZZ", min=30, pts=10 if i < 20 else 40))
        db.commit()
        r = backtest(db, db.get(League, 1), days=21, now_utc=datetime(2026, 11, 20, 15))
        assert r["games_tested"] > 0
        best = r["results"][0]
        assert best["name"] in ("Hot hand", "More recent")
        apply_weights(db, best["weights"])
        assert [w for _, w, _ in load_windows(db)] == best["weights"]
        apply_weights(db, None)
        assert [w for _, w, _ in load_windows(db)] == [0.15, 0.25, 0.30, 0.30]


def test_tuned_weights_change_projections(small_league):
    with SessionLocal() as db:
        for i in range(3):
            db.add(GameLog(player_id=1, game_id=f"late{i}", date_et=f"2026-11-2{i}", team="AAA", min=30, pts=60))
        db.commit()
        lg = db.get(League, 1)
        base = project_players(db, lg, [101], datetime(2026, 11, 23).date())[101].fpts
        apply_weights(db, [0.4, 0.3, 0.2, 0.1])
        hot = project_players(db, lg, [101], datetime(2026, 11, 23).date())[101].fpts
        apply_weights(db, None)
    assert hot > base


def test_move_results_compare_added_and_dropped(small_league):
    with SessionLocal() as db:
        m = MoveLog(league_id=1, team_id=10, created_at=datetime(2026, 11, 9, 12), source="suggested", add_name="Streamer",
                    add_yahoo_id=201, drop_yahoo_id=103, drop_name="Weak", status="done")
        db.add(m)
        db.commit()
        p = performance(db, db.get(League, 1), [m])
    r = p["by_move"][m.id]
    # Both played 6 games since Nov 9: Streamer 18 FP each, Weak 10 FP each
    assert (r["added_fp"], r["dropped_fp"], r["net"]) == (108.0, 60.0, 48.0) and p["total_net"] == 48.0


def test_insights_api_and_mcp(season, monkeypatch):
    with TestClient(app) as client:
        def fake_get(url, params=None, headers=None, timeout=None):
            return client.get(url.replace(mcp_server.API, ""), params=params, headers=headers)

        monkeypatch.setattr(mcp_server.httpx, "get", fake_get)
        assert client.get("/api/playoff-odds").status_code == 200
        assert client.get("/api/summary").status_code == 200
        assert client.put("/api/summary/settings", json={"enabled": True, "time": "06:30", "horizon": "C"}).json()["time"] == "06:30"
        assert client.put("/api/summary/settings", json={"time": "25:00"}).status_code == 422
        assert client.get("/api/tuning").status_code == 200
        assert client.put("/api/tuning", json={"weights": [-1, 1, 1, 1]}).status_code == 422
        assert client.post("/api/imports/reprocess").json() == {"pages": 0, "errors": 0}
        assert mcp_server.get_playoff_odds()["playoff_spots"] == 2
        assert mcp_server.get_daily_summary()["items"]
        with SessionLocal() as db:
            db.merge(AppSetting(key="summary_settings", value=None))
            db.commit()
