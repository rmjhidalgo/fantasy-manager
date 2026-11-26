"""Every team's roster in the active league.

Your own team (and any team whose page you saved) comes from its roster page, which
also knows who sits in IL slots. Other teams come from the "Taken" player lists
(owner of each player). Newer transactions on the League page are applied on top.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FantasyTeam, League, Ownership, Player, RosterSlot
from app.engine.pool import recent_moves
from app.nba.matching import norm_name

IL_SLOTS = {"IL", "IL+", "NA"}


def scheduled_opponent(db: Session, league: League, team_id: int, week: int) -> int | None:
    """Who a team plays in a week: from a saved Matchup page, else from the season schedule (League page → Schedule tab)."""
    from app.db.models import Matchup, ScheduleWeek

    mu = db.get(Matchup, (league.id, week, team_id))
    if mu is not None:
        return mu.opp_team_id
    row = db.get(ScheduleWeek, (league.id, week, team_id))
    return row.opp_team_id if row else None


def team_names(db: Session, league: League) -> dict[int, str]:
    return {t.team_id: t.name or f"Team {t.team_id}" for t in db.scalars(select(FantasyTeam).where(FantasyTeam.league_id == league.id))}


def team_rosters(db: Session, league: League) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """(players by team, players in IL slots by team). Player ids are Yahoo ids."""
    rosters: dict[int, set[int]] = {}
    il: dict[int, set[int]] = {}
    slot_rows = db.scalars(select(RosterSlot).where(RosterSlot.league_id == league.id)).all()
    slot_at: dict[int, object] = {}
    for r in slot_rows:
        rosters.setdefault(r.team_id, set()).add(r.player_id)
        if r.slot in IL_SLOTS:
            il.setdefault(r.team_id, set()).add(r.player_id)
        if r.as_of and (r.team_id not in slot_at or r.as_of > slot_at[r.team_id]):
            slot_at[r.team_id] = r.as_of
    for o in db.scalars(select(Ownership).where(Ownership.league_id == league.id, Ownership.kind == "team")):
        if o.team_id is None:
            continue
        # A roster page newer than the Taken list wins for that team
        if o.team_id in slot_at and o.as_of and slot_at[o.team_id] >= o.as_of:
            continue
        rosters.setdefault(o.team_id, set()).add(o.player_id)

    # Transactions after the pages were saved
    moves = recent_moves(db, league)
    if moves:
        names = {p.id: norm_name(p.name) for p in db.scalars(select(Player).where(Player.id.in_({p for s in rosters.values() for p in s})))}
        owned_at = {o.player_id: o.as_of for o in db.scalars(select(Ownership).where(Ownership.league_id == league.id))}
        for team, ids in rosters.items():
            for pid in list(ids):
                mv = moves.get(names.get(pid, ""))
                at = owned_at.get(pid)
                if mv and mv.action == "drop" and at and mv.at > at:
                    ids.discard(pid)
    return rosters, il
