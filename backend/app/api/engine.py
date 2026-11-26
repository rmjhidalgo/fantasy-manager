"""API: NBA data status/refresh, player matching fixes, projections, lineup and matchup outlook."""

import json
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import func, select

from app.db import SessionLocal
from app import yahoo_links
from app.db.models import (
    AppSetting,
    FantasyTeam,
    GameLog,
    League,
    NbaGame,
    NbaPlayer,
    OutlookHistory,
    Ownership,
    Player,
    PlayerMap,
    RosterSlot,
)
from app.engine.alerts import LONG_OUT
from app.engine.lineup import INACTIVE_SLOTS, Candidate, active_slots, optimize_day
from app.engine.projections import project_players
from app.engine.schedule import Schedule, today_et
from app.engine.simulator import matchup_outlook
from app.nba import matching, sync
from app.nba.client import NbaDataError

router = APIRouter(prefix="/api")


def _active_league(db) -> League:
    row = db.get(AppSetting, "active_league_id")
    lg = db.get(League, int(row.value)) if row and row.value else None
    if lg is None:
        raise HTTPException(404, "No league imported yet")
    return lg


def _iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def record_history(db, lg: League, team_id: int, o) -> None:
    """Keep one win-chance point per new data state (new matchup page or NBA refresh)."""
    refreshed = sync.refreshed_at()
    key = f"{o.as_of.isoformat() if o.as_of else '-'}|{refreshed.isoformat() if refreshed else '-'}"
    exists = db.scalar(select(OutlookHistory).where(
        OutlookHistory.league_id == lg.id, OutlookHistory.week == o.week, OutlookHistory.team_id == team_id,
        OutlookHistory.data_key == key))
    if exists is None:
        db.add(OutlookHistory(league_id=lg.id, week=o.week, team_id=team_id, data_key=key,
                              computed_at=datetime.now(UTC).replace(tzinfo=None), win_prob=o.win_prob,
                              my_final=o.me.final_expected, opp_final=o.opp.final_expected))
        db.commit()


# ------------------------------------------------------------------ NBA data

@router.get("/nba/status")
def nba_status() -> dict:
    with SessionLocal() as db:
        season = db.get(AppSetting, "nba_season")
        games = db.scalar(select(func.count()).select_from(NbaGame))
        logs = db.scalar(select(func.count()).select_from(GameLog))
        mapped = {m.yahoo_id for m in db.scalars(select(PlayerMap).where(PlayerMap.nba_id.is_not(None)))}
        no_match = {m.yahoo_id for m in db.scalars(select(PlayerMap).where(PlayerMap.method == "none"))}
        rostered = {o.player_id for o in db.scalars(select(Ownership).where(Ownership.kind == "team"))}
        unmatched = []
        if logs:  # only meaningful once NBA data exists
            for p in db.scalars(select(Player)):
                if p.id in mapped or p.id in no_match:
                    continue
                unmatched.append(
                    {
                        "yahoo_id": p.id,
                        "name": p.name,
                        "nba_team": p.nba_team,
                        "rostered": p.id in rostered,
                        "candidates": [{"nba_id": c.id, "name": c.name, "team": c.team} for c in matching.candidates(p.name)],
                    }
                )
        unmatched.sort(key=lambda u: (not u["rostered"], u["name"]))
    return {
        "refreshed_at": _iso(sync.refreshed_at()),
        "season": season.value if season else None,
        "games": games,
        "game_logs": logs,
        "last_error": sync.last_error,
        "unmatched": unmatched,
    }


@router.post("/nba/refresh")
async def nba_refresh() -> dict:
    try:
        result = await run_in_threadpool(sync.refresh)
    except NbaDataError as e:
        sync.last_error = str(e)
        raise HTTPException(502, str(e)) from e
    sync.last_error = None
    return result


class PlayerMapBody(BaseModel):
    yahoo_id: int
    nba_id: int | None  # None = "this player has no NBA match"


@router.put("/player-map")
def set_player_map(body: PlayerMapBody) -> dict:
    with SessionLocal() as db:
        if db.get(Player, body.yahoo_id) is None:
            raise HTTPException(404, "Unknown Yahoo player")
        if body.nba_id is not None and db.get(NbaPlayer, body.nba_id) is None:
            raise HTTPException(404, "Unknown NBA player")
        row = db.get(PlayerMap, body.yahoo_id) or PlayerMap(yahoo_id=body.yahoo_id)
        row.nba_id = body.nba_id
        row.method = "manual" if body.nba_id is not None else "none"
        db.add(row)
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ outlook + lineup

@router.get("/outlook")
def outlook() -> dict:
    """This week's matchup projection plus projections for my roster."""
    with SessionLocal() as db:
        lg = _active_league(db)
        if not lg.my_team_id:
            return {"matchup": None, "roster": []}
        teams = {t.team_id: t.name for t in db.scalars(select(FantasyTeam).where(FantasyTeam.league_id == lg.id))}
        o = matchup_outlook(db, lg, lg.my_team_id)
        if o:
            record_history(db, lg, lg.my_team_id, o)
        today = today_et()
        roster = db.scalars(select(RosterSlot).where(RosterSlot.league_id == lg.id, RosterSlot.team_id == lg.my_team_id)).all()
        proj = o.projections if o else project_players(db, lg, [r.player_id for r in roster], today)

        games_left: dict[int, int] = {}
        if o:
            for d in o.me.days:
                for pid in d.pending:
                    games_left[pid] = games_left.get(pid, 0) + 1

        def side(t):
            return {
                "team_id": t.team_id,
                "name": teams.get(t.team_id),
                "current": t.current,
                "remaining_expected": t.remaining_expected,
                "final_expected": t.final_expected,
                "final_p10": t.final_p10,
                "final_p90": t.final_p90,
                "games_left": t.games_left,
                "days": [{"date": d.date, "expected": d.expected, "starters": len(d.lineup), "pending": len(d.pending)} for d in t.days],
            }

        return {
            "today": today.isoformat(),
            "matchup": o and {
                "week": o.week,
                "start_date": o.start_date,
                "end_date": o.end_date,
                "as_of": _iso(o.as_of),
                "win_prob": o.win_prob,
                "me": side(o.me),
                "opp": side(o.opp),
                "notes": o.notes,
            },
            "roster": [
                {
                    "player_id": r.player_id,
                    "slot": r.slot,
                    "name": proj[r.player_id].name if r.player_id in proj else str(r.player_id),
                    "fpts": proj[r.player_id].fpts if r.player_id in proj else None,
                    "sd": proj[r.player_id].sd if r.player_id in proj else None,
                    "play_prob": proj[r.player_id].play_prob if r.player_id in proj else None,
                    "source": proj[r.player_id].source if r.player_id in proj else "none",
                    "recent_mpg": proj[r.player_id].recent_mpg if r.player_id in proj else None,
                    "season_mpg": proj[r.player_id].season_mpg if r.player_id in proj else None,
                    "games_left": games_left.get(r.player_id, 0) if o else None,
                }
                for r in roster
            ],
        }


@router.get("/lineup")
def lineup(day: str | None = None) -> dict:
    """Best lineup for my team on a given day (default: today, US Eastern), compared with the imported one."""
    with SessionLocal() as db:
        lg = _active_league(db)
        if not lg.my_team_id:
            raise HTTPException(404, "Your team isn't known yet: import a page from your league")
        d = date.fromisoformat(day) if day else today_et()
        settings = json.loads(lg.settings_json) if lg.settings_json else {}
        slots = active_slots(settings.get("roster_positions"))
        roster = db.scalars(select(RosterSlot).where(RosterSlot.league_id == lg.id, RosterSlot.team_id == lg.my_team_id)).all()
        proj = project_players(db, lg, [r.player_id for r in roster], today_et())
        sched = Schedule(db, d - timedelta(days=1), d)
        now = datetime.now(UTC).replace(tzinfo=None)
        cands, info = [], {}
        open_slots = list(slots)
        locked: dict[int, str] = {}
        for r in roster:
            p = proj.get(r.player_id)
            if not p:
                continue
            g = sched.game(p.nba_team, d)
            prob = p.play_prob_on(sched.is_back_to_back(p.nba_team, d)) if g else 0.0
            started = bool(g and (g.status != 1 or (g.start_utc and g.start_utc <= now)))
            info[r.player_id] = {
                "player_id": r.player_id,
                "name": p.name,
                "positions": p.positions,
                "status": p.status,
                "current_slot": r.slot,
                "game": g and {
                    "opponent": g.away if g.home == p.nba_team else f"@{g.home}",
                    "start_utc": _iso(g.start_utc),
                    "final": g.status == 3,
                    "started": started,
                },
                "expected": round(prob * p.fpts, 1) if g else 0.0,
            }
            if started:
                # Yahoo locks a player once his game starts: he stays where he is.
                if r.slot in open_slots:
                    open_slots.remove(r.slot)
                    locked[r.player_id] = r.slot
            elif g:
                cands.append(Candidate(r.player_id, p.positions, prob * p.fpts))
        best = optimize_day(open_slots, cands)
        best.assignments.update(locked)
        best.expected += sum(info[pid]["expected"] for pid in locked)
        rows = []
        for pid, x in info.items():
            new = best.assignments.get(pid)
            was_active = x["current_slot"] not in INACTIVE_SLOTS
            change = None
            if new and not was_active:
                change = "start"
            elif not new and was_active and x["game"]:
                change = "bench"
            elif not new and was_active and not x["game"]:
                change = "no game"
            rows.append({**x, "best_slot": new, "change": change, "locked": pid in locked or bool(x["game"] and x["game"]["started"])})
        order = {s: i for i, s in enumerate(slots)}
        rows.sort(key=lambda r: (r["best_slot"] is None, order.get(r["best_slot"] or "", 99), -r["expected"]))
        current_expected = sum(info[pid]["expected"] for pid, x in info.items() if x["current_slot"] not in INACTIVE_SLOTS and x["game"])

        # IL moves: long-term injured players taking a regular spot, and healthy players stuck in an IL slot
        il_slots = sum(1 for s in settings.get("roster_positions") or [] if s in ("IL", "IL+"))
        il_used = sum(1 for r in roster if r.slot in ("IL", "IL+"))
        il_moves = []
        for r in roster:
            p = proj.get(r.player_id)
            if not p:
                continue
            if r.slot in ("IL", "IL+") and p.status not in LONG_OUT | {"D", "Q", "GTD", "P"}:
                il_moves.append({"player_id": r.player_id, "name": p.name, "move": "activate",
                                 "reason": "No injury tag any more: Yahoo blocks adds/drops until he leaves the IL slot."})
            elif r.slot not in ("IL", "IL+") and p.status in LONG_OUT and il_used < il_slots:
                il_moves.append({"player_id": r.player_id, "name": p.name, "move": "to IL",
                                 "reason": f"Tagged {p.status}: an IL slot is free, which opens a roster spot for a pickup."})
                il_used += 1
        return {
            "date": d.isoformat(),
            "slots": slots,
            "best_expected": round(best.expected, 1),
            "current_expected": round(current_expected, 1),
            "players": rows,
            "il_moves": il_moves,
            "yahoo_url": yahoo_links.team_url(lg.id, lg.my_team_id, d.isoformat()),
        }
