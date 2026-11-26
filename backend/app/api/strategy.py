"""API: trades, schedule grid, player search/comparison, opponent scouting, scoring profile."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import yahoo_links
from app.api.engine import _active_league
from app.db import SessionLocal
from app.engine.rosters import team_names, team_rosters
from app.engine.strategy import compare_players, player_search, schedule_grid, scoring_profile, scout_opponent
from app.engine.trades import analyze_trade, build_world, find_trades

router = APIRouter(prefix="/api")
HORIZON = Query("C", pattern=r"^[ABCD]$")


def _league_team(db):
    lg = _active_league(db)
    if not lg.my_team_id:
        raise HTTPException(404, "Your team isn't known yet: import a page from your league")
    return lg, lg.my_team_id


@router.get("/teams")
def teams() -> dict:
    """Every team with its roster (for the trade analyzer)."""
    with SessionLocal() as db:
        lg, me = _league_team(db)
        w = build_world(db, lg, me, "C")
        names = team_names(db, lg)
        out = []
        for tid, ids in sorted(team_rosters(db, lg)[0].items()):
            players = sorted((w.proj[p] for p in ids if p in w.proj), key=lambda p: -p.fpts)
            out.append({"id": tid, "name": names.get(tid), "is_me": tid == me,
                        "players": [{"id": p.yahoo_id, "name": p.name, "nba_team": p.nba_team, "positions": p.positions,
                                     "status": p.status, "fpts": p.fpts} for p in players]})
        return {"teams": out}


class TradeBody(BaseModel):
    other_team: int
    give: list[int] = Field(min_length=1, max_length=5)
    get: list[int] = Field(min_length=1, max_length=5)
    horizon: str = Field("C", pattern=r"^[ABCD]$")


@router.post("/trade/analyze")
def trade_analyze(body: TradeBody) -> dict:
    with SessionLocal() as db:
        lg, me = _league_team(db)
        if body.other_team == me:
            raise HTTPException(422, "Pick another team to trade with.")
        try:
            r = analyze_trade(db, lg, me, body.other_team, body.give, body.get, body.horizon)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    r["yahoo_url"] = yahoo_links.team_url(lg.id, body.other_team)
    return r


# GET variant, so read-only clients (the MCP server) can analyze too
@router.get("/trade/analyze")
def trade_analyze_get(other_team: int, give: list[int] = Query(...), get: list[int] = Query(...), horizon: str = HORIZON) -> dict:
    return trade_analyze(TradeBody(other_team=other_team, give=give, get=get, horizon=horizon))


@router.get("/trade/find")
def trade_find(horizon: str = HORIZON, limit: int = Query(10, ge=1, le=30)) -> dict:
    with SessionLocal() as db:
        lg, me = _league_team(db)
        r = find_trades(db, lg, me, horizon, limit=limit)
    for t in r["trades"]:
        t["yahoo_url"] = yahoo_links.team_url(lg.id, t["team"]["id"])
    return r


@router.get("/schedule")
def schedule() -> dict:
    with SessionLocal() as db:
        lg, me = _league_team(db)
        return schedule_grid(db, lg, me)


@router.get("/players/search")
def search(q: str = Query(min_length=2, max_length=50)) -> dict:
    with SessionLocal() as db:
        lg, _ = _league_team(db)
        return {"players": player_search(db, lg, q)}


@router.get("/players/compare")
def compare(ids: list[int] = Query(..., min_length=1, max_length=4)) -> dict:
    with SessionLocal() as db:
        lg, me = _league_team(db)
        return compare_players(db, lg, me, ids)


@router.get("/scouting")
def scouting() -> dict:
    with SessionLocal() as db:
        lg, me = _league_team(db)
        return scout_opponent(db, lg, me)


@router.get("/scoring-profile")
def profile() -> dict:
    with SessionLocal() as db:
        lg, me = _league_team(db)
        return scoring_profile(db, lg, me)
