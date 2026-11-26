"""API: free agent finder, streaming planner, adds used, alerts, and the full matchup view."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import yahoo_links
from app.api.engine import _active_league, _iso, record_history
from app.db import SessionLocal
from app.db.models import FantasyTeam, MoveLog, OutlookHistory
from app.engine.movelog import log_move, my_transactions, performance, resolve
from app.engine.adds import adds_used, set_adds_used
from app.engine.alerts import build_alerts
from app.engine.freeagents import current_week, rank_free_agents
from app.engine.schedule import today_et
from app.engine.simulator import matchup_outlook
from app.engine.streaming import streaming_plan
from app.engine.suggest import suggest_moves
from app.engine.untouchables import get_untouchables, set_untouchables

router = APIRouter(prefix="/api")


def _my_team(lg) -> int:
    if not lg.my_team_id:
        raise HTTPException(404, "Your team isn't known yet: import a page from your league")
    return lg.my_team_id


@router.get("/free-agents")
def free_agents(window: str = Query("week", pattern=r"^(week|7|14)$"), position: str | None = None) -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        team_id = _my_team(lg)
        r = rank_free_agents(db, lg, team_id, window, position or None)
    for p in r["players"]:
        p["yahoo_url"] = yahoo_links.player_url(lg.id, p["yahoo_id"], p["name"])
    r["pool"]["available_as_of"] = _iso(r["pool"]["available_as_of"])
    r["pool"]["rostered_as_of"] = _iso(r["pool"]["rostered_as_of"])
    r["available_url"] = f"{yahoo_links.BASE}/{lg.id}/players"
    return r


def _adds(db, lg, team_id) -> dict:
    week, start, end = current_week(db, lg, team_id, today_et())
    return adds_used(db, lg, team_id, week, start, end)


@router.get("/adds")
def get_adds() -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        return _adds(db, lg, _my_team(lg))


class AddsBody(BaseModel):
    week: int
    used: int | None  # None = forget my entry, use the count from transactions


@router.put("/adds")
def put_adds(body: AddsBody) -> dict:
    if body.used is not None and not 0 <= body.used <= 50:
        raise HTTPException(422, "Adds used must be between 0 and 50")
    with SessionLocal() as db:
        lg = _active_league(db)
        set_adds_used(db, lg, body.week, body.used)
        return _adds(db, lg, _my_team(lg))


@router.get("/streaming")
def streaming(adds_left: int | None = None) -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        team_id = _my_team(lg)
        adds = _adds(db, lg, team_id)
        left = adds_left if adds_left is not None else (adds["left"] if adds["left"] is not None else 3)
        r = streaming_plan(db, lg, team_id, max(0, min(left, 10)))
    for m in r["moves"]:
        m["yahoo_url"] = yahoo_links.player_url(lg.id, m["add"]["yahoo_id"], m["add"]["name"])
    r["adds"] = adds
    return r


@router.get("/suggestions")
def suggestions(horizon: str = Query("A", pattern=r"^[ABCD]$")) -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        team_id = _my_team(lg)
        r = suggest_moves(db, lg, team_id, horizon)
    for m in r["moves"]:
        m["yahoo_url"] = yahoo_links.player_url(lg.id, m["add"]["yahoo_id"], m["add"]["name"])
    r["team_url"] = yahoo_links.team_url(lg.id, team_id)
    return r


class UntouchableBody(BaseModel):
    player_ids: list[int]


@router.get("/untouchables")
def get_untouchable() -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        return {"player_ids": sorted(get_untouchables(db, lg.id, _my_team(lg)))}


@router.put("/untouchables")
def put_untouchable(body: UntouchableBody) -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        set_untouchables(db, lg.id, _my_team(lg), set(body.player_ids))
        return {"player_ids": sorted(get_untouchables(db, lg.id, _my_team(lg)))}


class MoveLogBody(BaseModel):
    source: str = Field(pattern=r"^(suggested|free agents|streaming)$")
    add_name: str = Field(min_length=1, max_length=100)
    add_yahoo_id: int | None = None
    add_nba_id: int | None = None
    drop_yahoo_id: int | None = None
    drop_name: str | None = Field(default=None, max_length=100)
    gain: float | None = None
    horizon: str | None = Field(default=None, pattern=r"^[ABCD]$")


@router.post("/move-log")
def add_move_log(body: MoveLogBody) -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        row = log_move(db, lg, _my_team(lg), **body.model_dump())
        return {"id": row.id}


@router.get("/move-log")
def get_move_log() -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        team_id = _my_team(lg)
        resolve(db, lg, team_id)
        rows = db.scalars(select(MoveLog).where(MoveLog.league_id == lg.id, MoveLog.team_id == team_id)
                          .order_by(MoveLog.created_at.desc()).limit(100)).all()
        perf = performance(db, lg, list(rows))
        return {
            "performance": {"total_net": perf["total_net"], "moves_counted": perf["moves_counted"]},
            "moves": [
                {
                    "id": m.id, "created_at": _iso(m.created_at), "source": m.source, "horizon": m.horizon,
                    "add_name": m.add_name, "drop_name": m.drop_name, "gain": m.gain, "status": m.status,
                    "resolved_at": _iso(m.resolved_at), "note": m.note, "result": perf["by_move"].get(m.id),
                    "yahoo_url": yahoo_links.player_url(lg.id, m.add_yahoo_id, m.add_name),
                }
                for m in rows
            ],
            "transactions": my_transactions(db, lg, team_id),
        }


class MoveStatusBody(BaseModel):
    status: str = Field(pattern=r"^(open|dismissed)$")


@router.put("/move-log/{move_id}")
def set_move_status(move_id: int, body: MoveStatusBody) -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        m = db.get(MoveLog, move_id)
        if m is None or m.league_id != lg.id:
            raise HTTPException(404, "Move not found")
        m.status = body.status
        m.resolved_at = datetime.now(UTC).replace(tzinfo=None) if body.status == "dismissed" else None
        m.note = None
        db.commit()
        return {"ok": True}


@router.get("/alerts")
def alerts() -> dict:
    with SessionLocal() as db:
        lg = _active_league(db)
        items = build_alerts(db, lg)
    for a in items:
        for h in a.get("next_man_up", []):
            h["yahoo_url"] = yahoo_links.player_url(lg.id, h["yahoo_id"], h["name"]) if h["available"] else None
    return {"league_id": lg.id, "alerts": items, "generated_at": _iso(datetime.now(UTC).replace(tzinfo=None))}


@router.get("/matchup")
def matchup() -> dict:
    """The full matchup view: day-by-day for both teams, each player's games, slot conflicts, win-chance history."""
    with SessionLocal() as db:
        lg = _active_league(db)
        team_id = _my_team(lg)
        o = matchup_outlook(db, lg, team_id)
        if o is None:
            return {"matchup": None}
        record_history(db, lg, team_id, o)
        names = {t.team_id: t.name for t in db.scalars(select(FantasyTeam).where(FantasyTeam.league_id == lg.id))}
        history = db.scalars(
            select(OutlookHistory)
            .where(OutlookHistory.league_id == lg.id, OutlookHistory.team_id == team_id, OutlookHistory.week == o.week)
            .order_by(OutlookHistory.computed_at)
        ).all()

        def side(t):
            players: dict[int, dict] = {}
            for d in t.days:
                for pid in set(d.lineup) | set(d.bench_with_game):
                    p = o.projections.get(pid)
                    row = players.setdefault(pid, {
                        "player_id": pid, "name": p.name if p else str(pid), "nba_team": p.nba_team if p else None,
                        "positions": p.positions if p else [], "status": p.status if p else None,
                        "fpts": p.fpts if p else None, "days": {}, "starts": 0, "benched": 0,
                    })
                    if pid in d.lineup:
                        state = "pending" if pid in d.pending else "final"
                        row["starts"] += 1 if state == "pending" else 0
                    else:
                        state = "bench"
                        row["benched"] += 1
                    row["days"][d.date] = state
            return {
                "team_id": t.team_id,
                "name": names.get(t.team_id),
                "current": t.current,
                "final_expected": t.final_expected,
                "final_p10": t.final_p10,
                "final_p90": t.final_p90,
                "games_left": t.games_left,
                "days": [
                    {"date": d.date, "expected": d.expected, "actual": d.actual, "starters": len(d.lineup),
                     "pending": len(d.pending), "conflicts": len(d.bench_with_game), "from_page": d.from_page}
                    for d in t.days
                ],
                "players": sorted(players.values(), key=lambda r: (-r["starts"], -(r["fpts"] or 0))),
            }

        return {
            "matchup": {
                "week": o.week,
                "start_date": o.start_date,
                "end_date": o.end_date,
                "as_of": _iso(o.as_of),
                "win_prob": o.win_prob,
                "me": side(o.me),
                "opp": side(o.opp),
                "notes": o.notes,
                "yahoo_url": yahoo_links.matchup_url(lg.id, o.week),
            },
            "history": [
                {"at": _iso(h.computed_at), "win_prob": h.win_prob, "my_final": h.my_final, "opp_final": h.opp_final}
                for h in history
            ],
        }
