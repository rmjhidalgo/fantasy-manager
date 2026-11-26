"""API: playoff odds, daily summary (+ its settings), projection tuning."""

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.api.engine import _active_league
from app.api.engine import lineup as lineup_today
from app.db import SessionLocal
from app.engine.playoffs import playoff_odds
from app.engine.projections import load_windows
from app.engine.summary import build_summary, get_settings, set_settings
from app.engine.tuning import CANDIDATES, apply_weights, backtest

router = APIRouter(prefix="/api")


def _league_team(db):
    lg = _active_league(db)
    if not lg.my_team_id:
        raise HTTPException(404, "Your team isn't known yet: import a page from your league")
    return lg, lg.my_team_id


@router.get("/playoff-odds")
def odds() -> dict:
    with SessionLocal() as db:
        lg, me = _league_team(db)
        return playoff_odds(db, lg, me)


@router.get("/summary")
def summary() -> dict:
    try:
        lu = lineup_today()
    except HTTPException:
        lu = None
    with SessionLocal() as db:
        lg, me = _league_team(db)
        return build_summary(db, lg, me, lineup_today=lu)


@router.get("/summary/settings")
def summary_settings() -> dict:
    with SessionLocal() as db:
        return get_settings(db)


class SummarySettings(BaseModel):
    enabled: bool = True
    time: str = Field("07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    horizon: str = Field("A", pattern=r"^[ABCD]$")


@router.put("/summary/settings")
def put_summary_settings(body: SummarySettings) -> dict:
    with SessionLocal() as db:
        return set_settings(db, body.enabled, body.time, body.horizon)


@router.get("/tuning")
async def tuning(days: int = 21) -> dict:
    def run() -> dict:
        with SessionLocal() as db:
            lg, _ = _league_team(db)
            return backtest(db, lg, days=max(7, min(days, 60)))

    return await run_in_threadpool(run)


class TuningBody(BaseModel):
    weights: list[float] | None = Field(default=None, min_length=4, max_length=4)


@router.put("/tuning")
def set_tuning(body: TuningBody) -> dict:
    if body.weights is not None and (any(w < 0 for w in body.weights) or sum(body.weights) <= 0):
        raise HTTPException(422, "Weights must be positive")
    with SessionLocal() as db:
        return {"weights": apply_weights(db, body.weights), "defaults": CANDIDATES["Standard"]}


@router.get("/tuning/current")
def current_tuning() -> dict:
    with SessionLocal() as db:
        return {"weights": [w for _, w, _ in load_windows(db)], "defaults": CANDIDATES["Standard"]}
