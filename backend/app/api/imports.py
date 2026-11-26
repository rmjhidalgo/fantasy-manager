"""API: importing pages, the watched folder, and an overview of imported league data."""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from app.db import SessionLocal
from app.db.models import (
    AppSetting,
    FantasyTeam,
    ImportRecord,
    League,
    Matchup,
    Ownership,
    Player,
    PlayerStats,
    RosterSlot,
)
from app.importer import watcher
from app.importer.detect import PAGE_LABELS
from app.importer.service import import_bytes

router = APIRouter(prefix="/api")

MAX_FILE_BYTES = 40 * 1024 * 1024


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _get_setting(db, key: str) -> str | None:
    s = db.get(AppSetting, key)
    return s.value if s else None


def _set_setting(db, key: str, value: str | None) -> None:
    s = db.get(AppSetting, key)
    if s is None:
        db.add(AppSetting(key=key, value=value))
    else:
        s.value = value
    db.commit()


# ------------------------------------------------------------------ import

@router.post("/import")
async def import_files(
    files: list[UploadFile] = File(...),
    last_modified: list[int] = Form(default=[]),
) -> dict:
    """Import one or more saved pages. `last_modified` (ms since epoch, one per file) is
    the file's modified time from the browser, used when the page itself has no save time."""
    results = []
    for i, f in enumerate(files):
        data = await f.read(MAX_FILE_BYTES + 1)
        name = f.filename or "page"
        if len(data) > MAX_FILE_BYTES:
            results.append({"filename": name, "status": "unsupported", "summary": "File is too large to be a saved page.", "warnings": []})
            continue
        fallback = None
        if i < len(last_modified) and last_modified[i] > 0:
            fallback = datetime.fromtimestamp(last_modified[i] / 1000, UTC).replace(tzinfo=None)
        results.append(import_bytes(data, name, source="upload", fallback_saved_at=fallback).to_dict())
    return {"results": results}


@router.get("/imports")
def list_imports(limit: int = 50) -> dict:
    with SessionLocal() as db:
        rows = db.scalars(select(ImportRecord).order_by(ImportRecord.id.desc()).limit(min(limit, 500))).all()
        return {
            "imports": [
                {
                    "filename": r.filename,
                    "source": r.source,
                    "status": r.status,
                    "page_label": PAGE_LABELS.get(r.page_type or "", None),
                    "saved_at": _iso(r.saved_at),
                    "imported_at": _iso(r.imported_at),
                    "message": r.message,
                }
                for r in rows
            ]
        }


# ------------------------------------------------------------------ watched folder

class WatchFolderBody(BaseModel):
    folder: str | None


@router.get("/watch-folder")
def get_watch_folder() -> dict:
    with SessionLocal() as db:
        saved = _get_setting(db, "watch_folder")
    return {"configured": saved, **watcher.status(), "recent": watcher.recent[:20]}


@router.put("/watch-folder")
def set_watch_folder(body: WatchFolderBody) -> dict:
    folder = (body.folder or "").strip().strip('"') or None
    try:
        watcher.start(folder)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    with SessionLocal() as db:
        _set_setting(db, "watch_folder", folder)
    return get_watch_folder()


def start_saved_watcher() -> None:
    with SessionLocal() as db:
        folder = _get_setting(db, "watch_folder")
    if folder:
        try:
            watcher.start(folder)
        except ValueError:
            pass  # folder was removed; the Import screen shows it isn't running


# ------------------------------------------------------------------ leagues + overview

class ActiveLeagueBody(BaseModel):
    league_id: int


@router.get("/leagues")
def list_leagues() -> dict:
    with SessionLocal() as db:
        active = _get_setting(db, "active_league_id")
        leagues = db.scalars(select(League).order_by(League.id)).all()
        out = []
        for lg in leagues:
            my = db.get(FantasyTeam, (lg.id, lg.my_team_id)) if lg.my_team_id else None
            out.append({"id": lg.id, "name": lg.name, "my_team_id": lg.my_team_id, "my_team_name": my.name if my else None, "active": str(lg.id) == active})
        return {"leagues": out}


@router.put("/active-league")
def set_active_league(body: ActiveLeagueBody) -> dict:
    with SessionLocal() as db:
        if db.get(League, body.league_id) is None:
            raise HTTPException(404, "League not imported yet")
        _set_setting(db, "active_league_id", str(body.league_id))
    return list_leagues()


@router.get("/overview")
def overview() -> dict:
    """Everything imported so far for the active league, with how fresh each part is."""
    with SessionLocal() as db:
        active = _get_setting(db, "active_league_id")
        if not active:
            return {"league": None}
        lg = db.get(League, int(active))
        if lg is None:
            return {"league": None}
        lid, me = lg.id, lg.my_team_id
        teams = {t.team_id: t for t in db.scalars(select(FantasyTeam).where(FantasyTeam.league_id == lid))}
        settings = json.loads(lg.settings_json) if lg.settings_json else None

        # My roster with season stats
        window = db.scalar(
            select(PlayerStats.window).where(PlayerStats.league_id == lid).order_by(PlayerStats.as_of.desc()).limit(1)
        )
        slots = db.scalars(select(RosterSlot).where(RosterSlot.league_id == lid, RosterSlot.team_id == me)).all() if me else []
        slot_order = {s: i for i, s in enumerate(["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "BN", "IL", "IL+"])}
        roster = []
        for s in sorted(slots, key=lambda s: slot_order.get(s.slot, 99)):
            p = db.get(Player, s.player_id)
            st = db.get(PlayerStats, (lid, s.player_id, window)) if window else None
            roster.append(
                {
                    "player_id": s.player_id,
                    "slot": s.slot,
                    "name": p.name if p else str(s.player_id),
                    "nba_team": p.nba_team if p else None,
                    "positions": p.positions if p else None,
                    "status": p.status if p else None,
                    "gp": st.gp if st else None,
                    "fpts": st.fpts if st else None,
                    "mpg": st.mpg if st else None,
                }
            )
        roster_as_of = max((s.as_of for s in slots if s.as_of), default=None)

        # Current matchup = latest week stored for my team
        mu = db.scalar(select(Matchup).where(Matchup.league_id == lid, Matchup.team_id == me).order_by(Matchup.week.desc()).limit(1)) if me else None
        matchup = None
        if mu:
            matchup = {
                "week": mu.week,
                "start_date": mu.start_date,
                "end_date": mu.end_date,
                "my_score": mu.score,
                "opp_score": mu.opp_score,
                "opp_team_id": mu.opp_team_id,
                "opp_name": teams[mu.opp_team_id].name if mu.opp_team_id in teams else None,
                "as_of": _iso(mu.as_of),
            }

        own_counts = dict(
            db.execute(select(Ownership.kind, func.count()).where(Ownership.league_id == lid).group_by(Ownership.kind)).all()
        )
        own_as_of = db.scalar(select(func.max(Ownership.as_of)).where(Ownership.league_id == lid))
        stats_as_of = db.scalar(select(func.max(PlayerStats.as_of)).where(PlayerStats.league_id == lid))
        roster_spots = len([p for p in (settings or {}).get("roster_positions", [])])

        standings = sorted(
            (
                {"team_id": t.team_id, "name": t.name, "rank": t.rank, "wins": t.wins, "losses": t.losses, "ties": t.ties,
                 "points_for": t.points_for, "waiver_priority": t.waiver_priority, "moves": t.moves, "is_me": t.team_id == me}
                for t in teams.values() if t.rank is not None
            ),
            key=lambda r: r["rank"],
        )

        return {
            "league": {"id": lid, "name": lg.name, "my_team_id": me, "my_team_name": teams[me].name if me in teams else None},
            "settings": settings and {k: settings.get(k) for k in ("scoring", "roster_positions", "max_adds_per_week", "playoff_weeks", "trade_end_date")},
            "freshness": {
                "settings": _iso(lg.settings_as_of),
                "standings": _iso(lg.standings_as_of),
                "my_roster": _iso(roster_as_of),
                "matchup": matchup and matchup["as_of"],
                "players": _iso(own_as_of),
                "stats": _iso(stats_as_of),
            },
            "standings": standings,
            "my_roster": roster,
            "matchup": matchup,
            "players": {
                "rostered_known": own_counts.get("team", 0),
                "roster_spots_total": roster_spots * len(teams) if roster_spots and teams else None,
                "free_agents_known": own_counts.get("FA", 0),
                "waivers_known": own_counts.get("W", 0),
                "stats_window": window,
            },
        }
