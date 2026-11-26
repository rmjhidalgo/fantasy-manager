"""Injured players with an expected return date (ESPN's injury list): projections, trades, alerts."""

from datetime import date

import pytest
from test_moves import NOW, small_league  # noqa: F401  (fixture)
from test_suggest import with_matchup  # noqa: F401  (fixture)

from app.db import SessionLocal
from app.db.models import League, NbaInjury
from app.engine.alerts import build_alerts
from app.engine.projections import BACK_TO_BACK_FACTOR, PROB_AFTER_RETURN, injury_text, project_players
from app.engine.trades import analyze_trade
from app.nba import client, sync


def _injure(db, nba_id, name, status="Out", back="2026-11-27", what="Knee - Sprain"):
    db.add(NbaInjury(nba_id=nba_id, name=name, team="AAA", status=status, return_date=back, injury=what,
                     comment=f"{name} will miss time.", reported="2026-11-20"))


def test_injury_list_is_matched_to_nba_players(small_league, monkeypatch):
    monkeypatch.setattr(client, "fetch_injuries", lambda: [
        {"name": "Star", "team": "AAA", "status": "Out", "return_date": "2026-11-27", "injury": "Knee",
         "comment": "c", "reported": "2026-11-20"},
        {"name": "Somebody Else", "team": "GS", "status": "Day-To-Day", "return_date": None, "injury": None,
         "comment": None, "reported": None},
    ])
    assert sync.refresh_injuries() == 2
    with SessionLocal() as db:
        rows = {i.name: i for i in db.query(NbaInjury)}
    assert rows["Star"].nba_id == 1 and rows["Somebody Else"].nba_id is None and rows["Somebody Else"].team == "GSW"


def test_out_until_expected_return_then_likely_to_play(small_league):
    with SessionLocal() as db:
        _injure(db, 1, "Star")  # Star: out until Fri 11/27 (no Yahoo tag)
        _injure(db, 2, "Big", status="Day-To-Day", back="2026-11-25", what="Illness")
        db.commit()
        proj = project_players(db, db.get(League, 1), [101, 102], date(2026, 11, 23))
    star, big = proj[101], proj[102]
    assert star.play_prob == 0.0 and star.available_from() == date(2026, 11, 27)
    assert star.play_prob_on(False, date(2026, 11, 26)) == 0.0
    assert star.play_prob_on(True, date(2026, 11, 27)) == pytest.approx(PROB_AFTER_RETURN * BACK_TO_BACK_FACTOR)
    assert big.play_prob_on(False, date(2026, 11, 24)) == 0.5 and big.available_from() is None
    assert injury_text(star, date(2026, 11, 23)) == "Out until about Nov 27 (Knee - Sprain)"
    assert injury_text(star, date(2026, 11, 28)) is None  # back already


def test_trade_counts_injured_player_only_after_return(two_teams_injured):
    with SessionLocal() as db:
        healthy = analyze_trade(db, db.get(League, 1), 10, 20, give=[103], get=[301], key="A", now_utc=NOW)
        _injure(db, 21, "Rival", back="2026-11-29")  # Rival out until Sunday: only his last game counts
        db.commit()
        hurt = analyze_trade(db, db.get(League, 1), 10, 20, give=[103], get=[301], key="A", now_utc=NOW)
    assert hurt["my_team"]["gain"] < healthy["my_team"]["gain"]
    assert hurt["get"][0]["games"] == 1 and healthy["get"][0]["games"] == 3
    assert hurt["get"][0]["injury"] == "Out until about Nov 29 (Knee - Sprain)"


@pytest.fixture
def two_teams_injured(with_matchup):
    return NOW


def test_alert_when_espn_says_out_before_yahoo_tags_him(small_league):
    with SessionLocal() as db:
        _injure(db, 1, "Star")
        db.commit()
        alerts = build_alerts(db, db.get(League, 1), now_utc=NOW)
    a = next(x for x in alerts if x["key"].startswith("out:101"))
    assert a["level"] == "danger" and "Out until about Nov 27" in a["detail"] and "Yahoo hasn't tagged him" in a["detail"]
