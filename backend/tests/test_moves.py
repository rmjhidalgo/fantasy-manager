"""Milestone 3 tests: available pool, free agent finder, streaming planner, adds, alerts (made-up data)."""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine, init_db
from app.db.models import (
    AppSetting,
    FantasyTeam,
    GameLog,
    League,
    NbaGame,
    NbaPlayer,
    Ownership,
    Player,
    PlayerMap,
    RosterSlot,
    Transaction,
)
from app.engine.adds import adds_used, parse_moves, transaction_date_et
from app.engine.alerts import build_alerts
from app.engine.freeagents import build_context, rank_free_agents
from app.engine.next_man_up import next_man_up
from app.engine.pool import available_pool
from app.engine.projections import ABSENT_PROBABILITY, BACK_TO_BACK_FACTOR, project_nba_players, project_players, virtual_id
from app.engine.streaming import plan_streams

SCORING = {"PTS": 1.0}
# Small league: 2 active slots + 1 bench = 3 regular roster spots, plus 1 IL
POSITIONS = ["PG", "Util", "BN", "IL"]
SETTINGS = {
    "scoring": SCORING, "roster_positions": POSITIONS, "max_adds_per_week": 3,
    "raw": {"Draft Time": "Sun Oct 11 10:00pm JST", "Waiver Time": "2 days"},
}
NOW = datetime(2026, 11, 23, 14, 0)  # Monday 11/23, 09:00 US Eastern: no games started yet
WEEK = ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27", "2026-11-28", "2026-11-29"]


def _history(db, nba_id: int, team: str, fp: float, n: int = 6):
    for i in range(n):
        db.add(GameLog(player_id=nba_id, game_id=f"h-{team}-{i}", date_et=f"2026-11-{10 + i:02d}", team=team, min=30, pts=fp))


def _team_games(db, team: str, days: list[str], opp: str = "ZZZ"):
    for d in days:
        db.add(NbaGame(id=f"{team}-{d}", date_et=d, start_utc=datetime.fromisoformat(d + "T23:00"), home=team, away=opp, status=1))


def _yahoo(db, yid, nba_id, name, team, positions, slot=None, status=None, kind=None, team_id=10, as_of=NOW):
    db.add(Player(id=yid, name=name, nba_team=team, positions=positions, status=status, as_of=as_of))
    db.add(NbaPlayer(id=nba_id, name=name, team=team))
    db.add(PlayerMap(yahoo_id=yid, nba_id=nba_id, method="auto"))
    if slot:
        db.add(RosterSlot(league_id=1, team_id=team_id, player_id=yid, slot=slot, as_of=as_of))
    if kind == "team" or slot:
        db.add(Ownership(league_id=1, player_id=yid, kind="team", team_id=team_id, as_of=as_of))
    elif kind:
        db.add(Ownership(league_id=1, player_id=yid, kind=kind, as_of=as_of))


@pytest.fixture
def small_league(fresh_db):
    """My roster: PG 'Star' (30 FP, 2 games), C 'Big' (20 FP, 2 games), C 'Weak' (10 FP, 2 games).
    Available: 'Streamer' C (18 FP, 4 games, FA on a page), 'Hidden' (NBA-only, 15 FP, 4 games)."""
    with SessionLocal() as db:
        db.add(League(id=1, name="Test", my_team_id=10, settings_json=json.dumps(SETTINGS)))
        db.add(AppSetting(key="active_league_id", value="1"))
        db.add(FantasyTeam(league_id=1, team_id=10, name="Mine"))
        _yahoo(db, 101, 1, "Star", "AAA", "PG", slot="PG")
        _yahoo(db, 102, 2, "Big", "BBB", "C", slot="Util")
        _yahoo(db, 103, 3, "Weak", "BBB", "C", slot="BN")
        _yahoo(db, 201, 11, "Streamer", "CCC", "C", kind="FA")
        db.add(NbaPlayer(id=12, name="Hidden Gem", team="DDD", position="G"))
        _history(db, 1, "AAA", 30)
        _history(db, 2, "BBB", 20)
        _history(db, 3, "BBB", 10)
        _history(db, 11, "CCC", 18)
        _history(db, 12, "DDD", 15)
        _team_games(db, "AAA", [WEEK[0], WEEK[3]])
        _team_games(db, "BBB", [WEEK[0], WEEK[3]])
        _team_games(db, "CCC", [WEEK[1], WEEK[2], WEEK[4], WEEK[5]])
        _team_games(db, "DDD", [WEEK[1], WEEK[2], WEEK[4], WEEK[6]])
        db.commit()
    return NOW


# ---------------------------------------------------------------- transactions

def test_parse_moves():
    d = "Grayson Allen CHA - SG,SF O To Waivers Buddy Hield CHI - SG,SF Free Agent"
    assert parse_moves(d) == [("Grayson Allen", "drop"), ("Buddy Hield", "add")]
    assert parse_moves("Danny Wolf BKN - PF,C To Waivers") == [("Danny Wolf", "drop")]


def test_transaction_time_converted_to_us_eastern():
    # 7:41 am in Japan on Nov 26 is still Nov 25 in New York
    assert transaction_date_et("Nov 26, 7:41 am", ZoneInfo("Asia/Tokyo"), date(2026, 11, 26)) == date(2026, 11, 25)
    assert transaction_date_et("Jan 2, 1:00 pm", ZoneInfo("Asia/Tokyo"), date(2026, 12, 30)) == date(2027, 1, 1)


def test_adds_counted_from_transactions_and_manual_entry_wins(small_league):
    with SessionLocal() as db:
        db.add(Transaction(league_id=1, team_name="Mine", when_text="Nov 24, 9:00 pm",
                           description="Streamer CCC - C Free Agent Weak BBB - C To Waivers", as_of=NOW))
        db.add(Transaction(league_id=1, team_name="Other", when_text="Nov 24, 9:00 pm",
                           description="Someone XXX - PG Free Agent", as_of=NOW))
        db.commit()
        lg = db.get(League, 1)
        a = adds_used(db, lg, 10, 6, date(2026, 11, 23), date(2026, 11, 29))
        assert (a["used"], a["left"], a["source"]) == (1, 2, "transactions")
        db.add(AppSetting(key="adds_used:1:6", value="3"))
        db.commit()
        a = adds_used(db, lg, 10, 6, date(2026, 11, 23), date(2026, 11, 29))
        assert (a["used"], a["left"], a["source"]) == (3, 0, "you")


# ---------------------------------------------------------------- pool

def test_pool_combines_pages_and_nba_data(small_league):
    with SessionLocal() as db:
        pool, info = available_pool(db, db.get(League, 1))
    by_id = {p.id: p for p in pool}
    assert by_id[201].source == "page" and by_id[201].kind == "FA"
    assert by_id[virtual_id(12)].source == "nba" and by_id[virtual_id(12)].kind == "?"
    assert 101 not in by_id and virtual_id(1) not in by_id  # rostered players never show up as available
    assert info.page_count == 1 and info.nba_count == 1 and info.rostered_count == 3


def test_pool_applies_newer_transactions(small_league):
    with SessionLocal() as db:
        # After the pages were saved: someone picked up Streamer, and Hidden Gem was dropped.
        db.add(Transaction(league_id=1, team_name="Other", when_text="Nov 24, 9:00 am",
                           description="Streamer CCC - C Free Agent Hidden Gem DDD - PG To Waivers", as_of=NOW))
        db.commit()
        pool, _ = available_pool(db, db.get(League, 1))
    by_id = {p.id: p for p in pool}
    assert 201 not in by_id
    gem = by_id[virtual_id(12)]
    assert gem.kind == "W" and gem.waiver_until == "2026-11-25"  # Nov 24 9am JST = Nov 23 ET, + 2 days


def test_nba_only_players_get_estimated_positions(small_league):
    with SessionLocal() as db:
        p = project_nba_players(db, db.get(League, 1), [12], date(2026, 11, 23))[virtual_id(12)]
    assert p.positions == ["PG", "SG"] and p.positions_estimated and p.fpts == pytest.approx(15)


def test_untagged_player_missing_team_games_is_doubtful(small_league):
    with SessionLocal() as db:
        for i in range(3):  # BBB played 3 more games without Weak
            db.add(NbaGame(id=f"miss{i}", date_et=f"2026-11-{17 + i}", home="BBB", away="ZZZ", status=3))
            db.add(GameLog(player_id=2, game_id=f"miss{i}", date_et=f"2026-11-{17 + i}", team="BBB", min=30, pts=20))
        for i in range(6):
            db.add(NbaGame(id=f"h-BBB-{i}", date_et=f"2026-11-{10 + i:02d}", home="BBB", away="ZZZ", status=3))
        db.commit()
        proj = project_players(db, db.get(League, 1), [102, 103], date(2026, 11, 23))
    assert proj[103].missed_streak == 3 and proj[103].play_prob == ABSENT_PROBABILITY
    assert proj[102].missed_streak == 0 and proj[102].play_prob == 0.97


# ---------------------------------------------------------------- free agents + streaming

def test_free_agents_ranked_by_points_added_to_my_lineup(small_league):
    with SessionLocal() as db:
        r = rank_free_agents(db, db.get(League, 1), 10, "week", now_utc=NOW)
    top = r["players"][0]
    # Streamer plays 4 days when my Util slot is otherwise empty; dropping Weak (bench, never starts) costs nothing.
    assert top["name"] == "Streamer" and top["drop_name"] == "Weak"
    # Tue+Wed and Fri+Sat are back-to-backs: the second nights count a little less
    assert top["gain"] == pytest.approx(0.97 * 18 * (2 + 2 * BACK_TO_BACK_FACTOR), abs=0.1)
    assert top["games"] == 4 and top["vs_drop"] == pytest.approx(8)
    assert r["open_spots"] == 0
    hidden = next(p for p in r["players"] if p["name"] == "Hidden Gem")
    assert hidden["source"] == "nba" and hidden["gain"] == pytest.approx(0.97 * 15 * (3 + BACK_TO_BACK_FACTOR), abs=0.1)


def test_waiver_player_counts_only_after_waivers_clear(small_league):
    with SessionLocal() as db:
        o = db.get(Ownership, (1, 201))
        o.kind, o.waiver_until = "W", "2026-11-26"
        db.commit()
        r = rank_free_agents(db, db.get(League, 1), 10, "week", now_utc=NOW)
    s = next(p for p in r["players"] if p["name"] == "Streamer")
    assert s["available_from"] == "2026-11-26" and s["games"] == 2  # only Fri + Sat remain


def test_streaming_chain_respects_adds_and_keeps_better_players(small_league):
    with SessionLocal() as db:
        ctx = build_context(db, db.get(League, 1), 10, "week", now_utc=NOW)
    moves, baseline, total = plan_streams(ctx, adds_left=2)
    assert 1 <= len(moves) <= 2
    assert total - baseline == pytest.approx(sum(m.gain for m in moves), abs=0.2)
    # Big (20 FP) and Star (30 FP) are better than both streamers: only Weak or a streamer is ever dropped
    assert all(m.drop in (103, 201, virtual_id(12)) for m in moves)
    assert moves[0].drop == 103
    none, b0, t0 = plan_streams(ctx, adds_left=0)
    assert none == [] and b0 == t0


# ---------------------------------------------------------------- alerts + next man up

def test_alerts_injury_il_and_empty_slots(small_league):
    with SessionLocal() as db:
        db.get(Player, 101).status = "O"
        db.commit()
        alerts = build_alerts(db, db.get(League, 1), now_utc=NOW)
    keys = [a["key"] for a in alerts]
    out = next(a for a in alerts if a["key"].startswith("out:101"))
    assert out["level"] == "danger" and "IL slot is free" in out["detail"]
    assert any(k.startswith("empty:2026-11-23") for k in keys)  # Star is out, so a slot is empty today
    assert any(k.startswith("adds:") for k in keys)


def test_alert_for_healthy_player_in_il_slot(small_league):
    with SessionLocal() as db:
        db.get(RosterSlot, (1, 10, 103)).slot = "IL"
        db.commit()
        alerts = build_alerts(db, db.get(League, 1), now_utc=NOW)
    assert any(a["key"] == "il-healthy:103" for a in alerts)


def test_next_man_up_finds_teammate_with_more_minutes(fresh_db):
    with SessionLocal() as db:
        db.add(League(id=1, settings_json=json.dumps(SETTINGS)))
        db.add(NbaPlayer(id=1, name="Starter", team="AAA"))
        db.add(NbaPlayer(id=2, name="Backup", team="AAA"))
        for i in range(6):
            db.add(NbaGame(id=f"g{i}", date_et=f"2026-11-{10 + i}", home="AAA", away="ZZZ", status=3))
            if i < 4:  # Starter played the first 4 games, then got hurt
                db.add(GameLog(player_id=1, game_id=f"g{i}", date_et=f"2026-11-{10 + i}", team="AAA", min=34, pts=25))
            db.add(GameLog(player_id=2, game_id=f"g{i}", date_et=f"2026-11-{10 + i}", team="AAA",
                           min=14 if i < 4 else 30, pts=6 if i < 4 else 18))
        db.commit()
        out = next_man_up(db, db.get(League, 1), 1, "AAA")
    assert [b.name for b in out] == ["Backup"]
    assert out[0].minutes_with == 14 and out[0].minutes_without == 30 and out[0].fpts_without == 18


# ---------------------------------------------------------------- database upgrade + API

def test_new_columns_added_to_existing_database(fresh_db):
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE nba_players"))
        conn.execute(text("CREATE TABLE nba_players (id INTEGER PRIMARY KEY, name VARCHAR, team VARCHAR)"))
    init_db()
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(nba_players)"))}
    assert "position" in cols


def test_api_endpoints_answer(small_league):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        fa = client.get("/api/free-agents", params={"window": "7"}).json()
        assert fa["players"] and fa["players"][0]["yahoo_url"].startswith("https://basketball.fantasysports.yahoo.com/nba/1/")
        assert client.get("/api/free-agents", params={"window": "99"}).status_code == 422
        assert "moves" in client.get("/api/streaming", params={"adds_left": 1}).json()
        assert "alerts" in client.get("/api/alerts").json()
        r = client.put("/api/adds", json={"week": 6, "used": 2})
        assert r.status_code == 200
