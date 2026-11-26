"""Engine tests with small made-up data (no internet, no saved pages needed)."""

import json
from datetime import date, datetime

import pytest

from app.db import SessionLocal
from app.db.models import AppSetting, GameLog, League, Matchup, NbaGame, NbaPlayer, Player, PlayerMap, RosterSlot
from app.engine.lineup import Candidate, active_slots, optimize_day
from app.engine.projections import BACK_TO_BACK_FACTOR, project_players
from app.engine.schedule import today_et
from app.engine.simulator import matchup_outlook
from app.nba import client, sync
from app.nba.matching import match_all, norm_name

SCORING = {"3PTM": 1.5, "PTS": 1.0, "REB": 1.2, "AST": 1.5, "ST": 3.0, "BLK": 3.0, "TO": -1.0}
SLOTS = ["PG", "SG", "G", "SF", "PF", "F", "C", "C", "Util", "Util", "BN", "BN", "BN", "IL", "IL"]


# ---------------------------------------------------------------- lineup optimizer

def test_active_slots_ignore_bench_and_il():
    assert active_slots(SLOTS) == ["PG", "SG", "G", "SF", "PF", "F", "C", "C", "Util", "Util"]
    assert len(active_slots(None)) == 10


def test_optimizer_respects_positions_and_picks_best():
    slots = ["PG", "C", "Util"]
    cands = [
        Candidate(1, ["PG"], 30),
        Candidate(2, ["PG"], 25),
        Candidate(3, ["C"], 20),
        Candidate(4, ["C"], 40),
        Candidate(5, ["SF"], 10),
    ]
    best = optimize_day(slots, cands)
    assert best.assignments == {1: "PG", 4: "C", 2: "Util"}
    assert best.expected == 95
    assert set(best.bench_with_game) == {3, 5}


def test_optimizer_uses_flexible_players_to_fit_more():
    # A PG/SG player must go to SG so that the PG-only player can play too.
    best = optimize_day(["PG", "SG"], [Candidate(1, ["PG", "SG"], 50), Candidate(2, ["PG"], 20)])
    assert best.assignments == {1: "SG", 2: "PG"}


def test_optimizer_skips_players_who_wont_play():
    best = optimize_day(["Util"], [Candidate(1, ["C"], 0.0)])
    assert best.assignments == {} and best.expected == 0


# ---------------------------------------------------------------- name matching

def test_norm_name():
    assert norm_name("Luka Dončić") == "luka doncic"
    assert norm_name("Jabari Smith Jr.") == "jabari smith"
    assert norm_name("De'Anthony Melton") == "deanthony melton"
    assert norm_name("Egor Dëmin") == "egor demin"


# ---------------------------------------------------------------- fake league helpers

def _log(pid, gid, day, pts, team="AAA", **kw):
    return GameLog(player_id=pid, game_id=gid, date_et=day, team=team, min=30, pts=pts, reb=kw.get("reb", 0),
                   ast=kw.get("ast", 0), stl=0, blk=0, tov=0, fg3m=0)


def _setup_league(db, now: datetime):
    db.add(League(id=1, name="Test", my_team_id=10, settings_json=json.dumps({"scoring": SCORING, "roster_positions": SLOTS})))
    db.add(AppSetting(key="active_league_id", value="1"))
    # Yahoo players: 101 (mine, team AAA), 201 (opponent, team BBB)
    db.add(Player(id=101, name="My Guy", nba_team="AAA", positions="PG", status=None, as_of=now))
    db.add(Player(id=201, name="Their Guy", nba_team="BBB", positions="C", status=None, as_of=now))
    db.add(PlayerMap(yahoo_id=101, nba_id=1, method="auto"))
    db.add(PlayerMap(yahoo_id=201, nba_id=2, method="auto"))
    db.add(RosterSlot(league_id=1, team_id=10, player_id=101, slot="PG", as_of=now))
    db.add(RosterSlot(league_id=1, team_id=20, player_id=201, slot="C", as_of=now))


@pytest.fixture
def league(fresh_db):
    now = datetime(2026, 11, 25, 15, 0)  # 10:00 US Eastern on Wed 11/25
    with SessionLocal() as db:
        _setup_league(db, now)
        # History: My Guy scores 20 then 40 (recent games count more), Their Guy steady 30.
        for i, d in enumerate(["2026-11-01", "2026-11-05", "2026-11-10"]):
            db.add(_log(1, f"h{i}", d, 20))
            db.add(_log(2, f"h{i}", d, 30, team="BBB"))
        for i, d in enumerate(["2026-11-20", "2026-11-22"]):
            db.add(_log(1, f"r{i}", d, 40))
            db.add(_log(2, f"r{i}", d, 30, team="BBB"))
        db.commit()
    return now


def test_projection_blends_recent_and_season(league):
    with SessionLocal() as db:
        proj = project_players(db, db.get(League, 1), [101, 201], date(2026, 11, 25))
    mine, theirs = proj[101], proj[201]
    assert theirs.fpts == pytest.approx(30)  # steady player: every window says 30
    # Season and last-30-days average 28; last 7 and 14 days average 40 but have only 2 games,
    # so those windows count less: (0.15*2/3*40 + 0.25*2/5*40 + 0.30*5/8*28 + 0.30*5/10*28) / total weight
    w = [0.15 * 2 / 3, 0.25 * 2 / 5, 0.30 * 5 / 8, 0.30 * 5 / 10]
    expected = (w[0] * 40 + w[1] * 40 + w[2] * 28 + w[3] * 28) / sum(w)
    assert mine.fpts == pytest.approx(expected, abs=0.01)
    assert 28 < mine.fpts < 40
    assert mine.source == "nba" and mine.games_used == 5
    assert mine.play_prob_on(True) == pytest.approx(mine.play_prob * BACK_TO_BACK_FACTOR)


def test_injury_tag_sets_chance_of_playing(league):
    with SessionLocal() as db:
        db.get(Player, 101).status = "O"
        db.commit()
        proj = project_players(db, db.get(League, 1), [101], date(2026, 11, 25))
    assert proj[101].play_prob == 0.0


def test_matchup_outlook_uses_real_results_then_simulates(league):
    now = league
    with SessionLocal() as db:
        # Week 11/23-11/29. Score saved Wed 11/25 10:00 ET: 100 vs 100.
        db.add(Matchup(league_id=1, week=6, team_id=10, opp_team_id=20, score=100, opp_score=100,
                       start_date="2026-11-23", end_date="2026-11-29", as_of=now))
        db.add(Matchup(league_id=1, week=6, team_id=20, opp_team_id=10, score=100, opp_score=100,
                       start_date="2026-11-23", end_date="2026-11-29", as_of=now))
        # Game that started BEFORE the save (already in the score): ignored.
        db.add(NbaGame(id="g0", date_et="2026-11-25", start_utc=datetime(2026, 11, 25, 14), home="AAA", away="BBB", status=3))
        # Next day: finished after the save -> real box score (My Guy 50, Their Guy 10).
        db.add(NbaGame(id="g1", date_et="2026-11-26", start_utc=datetime(2026, 11, 27, 0), home="AAA", away="BBB", status=3))
        db.add(_log(1, "g1", "2026-11-26", 50))
        db.add(_log(2, "g1", "2026-11-26", 10, team="BBB"))
        # Later: not played yet -> simulated
        db.add(NbaGame(id="g2", date_et="2026-11-28", start_utc=datetime(2026, 11, 29, 0), home="AAA", away="BBB", status=1))
        db.commit()
        o = matchup_outlook(db, db.get(League, 1), 10, now_utc=datetime(2026, 11, 27, 12))

    assert o.week == 6
    days = {d.date: d for d in o.me.days}
    assert days["2026-11-25"].lineup == {}  # g0 already counted in the saved score
    assert days["2026-11-26"].actual == 50 and days["2026-11-26"].pending == []
    assert days["2026-11-28"].pending == [101]
    assert o.me.final_expected == pytest.approx(100 + 50 + 0.97 * o.projections[101].fpts, abs=0.2)
    # Their Guy's 10-point game on 11/26 also lowers his projection for the rest of the week.
    assert o.projections[201].fpts < 30
    assert o.opp.final_expected == pytest.approx(100 + 10 + 0.97 * o.projections[201].fpts, abs=0.2)
    assert o.win_prob > 0.8  # +40 from the finished game is hard to overcome in one game
    assert o.me.games_left == 1 and o.opp.games_left == 1


def test_lineup_keeps_started_players_locked(league):
    from fastapi.testclient import TestClient

    from app.main import app

    with SessionLocal() as db:
        # A second PG on my bench; my starting PG's game has already started.
        db.add(Player(id=102, name="Bench Guy", nba_team="CCC", positions="PG", status=None))
        db.add(PlayerMap(yahoo_id=102, nba_id=3, method="auto"))
        db.add(RosterSlot(league_id=1, team_id=10, player_id=102, slot="BN"))
        for i, d in enumerate(["2026-11-20", "2026-11-22"]):
            db.add(_log(3, f"c{i}", d, 60, team="CCC"))  # Bench Guy projects far higher
        db.add(NbaGame(id="started", date_et="2026-11-24", start_utc=datetime(2026, 11, 24, 20), home="AAA", away="BBB", status=2))
        db.add(NbaGame(id="later", date_et="2026-11-24", start_utc=datetime(2099, 1, 1), home="CCC", away="DDD", status=1))
        db.commit()
    with TestClient(app) as client:
        r = client.get("/api/lineup", params={"day": "2026-11-24"}).json()
    rows = {p["player_id"]: p for p in r["players"]}
    assert rows[101]["locked"] and rows[101]["best_slot"] == "PG"  # can't be moved: game started
    assert rows[102]["best_slot"] in ("G", "Util")  # PG slot is taken by the locked player; he fits elsewhere
    assert rows[102]["change"] == "start"


def test_today_et_uses_us_eastern_dates():
    assert today_et(datetime(2026, 11, 26, 3, 0)) == date(2026, 11, 25)  # 22:00 ET the night before
    assert today_et(datetime(2026, 11, 26, 6, 0)) == date(2026, 11, 26)


# ---------------------------------------------------------------- NBA sync (downloads faked)

def test_sync_keeps_finished_games_only_and_matches_players(fresh_db, monkeypatch):
    sched = {
        "seasonYear": "2026-27",
        "gameDates": [
            {"games": [
                {"gameId": "0022600001", "gameDateEst": "2026-11-24T00:00:00Z", "gameDateTimeUTC": "2026-11-25T00:00:00Z",
                 "gameStatus": 2, "homeTeam": {"teamTricode": "AAA"}, "awayTeam": {"teamTricode": "BBB"}},
                {"gameId": "0022600002", "gameDateEst": "2026-11-25T00:00:00Z", "gameDateTimeUTC": "2026-11-26T00:00:00Z",
                 "gameStatus": 2, "homeTeam": {"teamTricode": "AAA"}, "awayTeam": {"teamTricode": "BBB"}},
                {"gameId": "0062600001", "gameDateEst": "2026-12-16T00:00:00Z", "gameDateTimeUTC": None,
                 "gameStatus": 1, "homeTeam": {"teamTricode": None}, "awayTeam": {"teamTricode": None}},
            ]}
        ],
    }
    base = {"TEAM_ABBREVIATION": "AAA", "MIN": 30, "PTS": 10, "REB": 5, "AST": 2, "STL": 1, "BLK": 0, "TOV": 1,
            "FG3M": 1, "FGM": 4, "FGA": 9, "FTM": 1, "FTA": 2, "OREB": 1, "DREB": 4, "PF": 2}
    logs = [
        {**base, "PLAYER_ID": 1, "PLAYER_NAME": "Luka Dončić", "GAME_ID": "0022600001", "GAME_DATE": "2026-11-24", "WL": "W"},
        {**base, "PLAYER_ID": 1, "PLAYER_NAME": "Luka Dončić", "GAME_ID": "0022600002", "GAME_DATE": "2026-11-25", "WL": None},
    ]
    players = [{"PERSON_ID": 1, "DISPLAY_FIRST_LAST": "Luka Dončić", "TEAM_ABBREVIATION": "AAA"}]
    monkeypatch.setattr(client, "fetch_schedule", lambda: sched)
    monkeypatch.setattr(client, "fetch_game_logs", lambda season: logs)
    monkeypatch.setattr(client, "fetch_players", lambda season: players)
    with SessionLocal() as db:
        db.add(Player(id=6014, name="Luka Doncic", nba_team="AAA", positions="PG,SG"))
        db.commit()

    result = sync.refresh()
    assert result["unmatched"] == 0
    with SessionLocal() as db:
        assert db.get(NbaGame, "0022600001").status == 3  # box score has a result -> finished
        assert db.get(NbaGame, "0022600002").status == 2  # still live
        assert db.get(NbaGame, "0062600001") is None  # teams not decided yet
        assert db.query(GameLog).count() == 1  # live game's partial line skipped
        assert db.get(PlayerMap, 6014).nba_id == 1
        assert db.get(NbaPlayer, 1).name == "Luka Dončić"


def test_manual_match_is_kept(fresh_db):
    with SessionLocal() as db:
        db.add(NbaPlayer(id=1, name="Jalen Smith", team="CHI"))
        db.add(NbaPlayer(id=2, name="Jalen Smith Jr", team="CHI"))
        db.add(Player(id=50, name="Jalen Smith", nba_team="CHI", positions="PF,C"))
        db.add(PlayerMap(yahoo_id=50, nba_id=2, method="manual"))
        db.commit()
    match_all()
    with SessionLocal() as db:
        assert db.get(PlayerMap, 50).nba_id == 2  # automatic matching doesn't override manual choices
