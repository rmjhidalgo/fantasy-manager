"""Who can be added: the pool of available players.

Two sources, combined:
1. "page": players listed as free agents (FA) or on waivers (W) on saved Yahoo player lists.
2. "nba": every NBA player who has played this season and isn't on any saved roster or
   player list. If all rostered players have been imported (the "Taken" pages), everyone
   else must be available. These have no Yahoo details: their positions are estimated
   from NBA.com, and they might be on waivers.

Transactions on the saved League page that happened after a player's ownership was saved
are applied on top: a player added since is taken; a player dropped since is on waivers.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GameLog, League, NbaPlayer, Ownership, Player, PlayerMap, Transaction
from app.engine.adds import parse_moves, transaction_time, waiver_days, yahoo_zone
from app.engine.projections import virtual_id
from app.engine.schedule import ET
from app.nba.matching import norm_name


@dataclass
class PoolPlayer:
    id: int  # Yahoo id, or virtual_id(nba_id)
    yahoo_id: int | None
    nba_id: int | None
    source: str  # "page" | "nba"
    kind: str  # "FA" | "W" | "?" (not on a saved page: free agent or waivers)
    waiver_until: str | None  # ISO date (waivers only)
    as_of: datetime | None
    note: str | None = None


@dataclass
class PoolInfo:
    page_count: int
    nba_count: int
    available_as_of: datetime | None  # newest saved Available list
    rostered_as_of: datetime | None  # oldest rostered-player data (the stalest part matters)
    rostered_count: int
    from_transactions: int = 0  # players whose status comes from a newer transaction


@dataclass
class RecentMove:
    action: str  # "add" | "drop"
    at: datetime  # UTC (naive)
    team_name: str | None


def recent_moves(db: Session, league: League) -> dict[str, RecentMove]:
    """Latest add/drop per player (normalised name) from imported transactions."""
    zone = yahoo_zone(league)
    latest: dict[str, RecentMove] = {}
    for t in db.scalars(select(Transaction).where(Transaction.league_id == league.id)):
        # the page's save time tells which year "Nov 26" is
        at = transaction_time(t.when_text, zone, (t.as_of or datetime.now(UTC)).date())
        if at is None:
            continue
        at_utc = at.astimezone(UTC).replace(tzinfo=None)
        for name, action in parse_moves(t.description):
            key = norm_name(name)
            if key not in latest or latest[key].at < at_utc:
                latest[key] = RecentMove(action, at_utc, t.team_name)
    return latest


def available_pool(db: Session, league: League) -> tuple[list[PoolPlayer], PoolInfo]:
    own = db.scalars(select(Ownership).where(Ownership.league_id == league.id)).all()
    maps = {m.yahoo_id: m.nba_id for m in db.scalars(select(PlayerMap)) if m.nba_id}
    names = {p.id: norm_name(p.name) for p in db.scalars(select(Player).where(Player.id.in_([o.player_id for o in own])))}
    moves = recent_moves(db, league)
    wait = timedelta(days=waiver_days(league))

    def waiver_end(at: datetime) -> str:
        return (at.replace(tzinfo=UTC).astimezone(ET).date() + wait).isoformat()

    pool: list[PoolPlayer] = []
    known_nba: set[int] = set()
    rostered_names: set[str] = set()
    rostered_count = 0
    changed = 0
    for o in own:
        nba = maps.get(o.player_id)
        if nba:
            known_nba.add(nba)
        mv = moves.get(names.get(o.player_id, ""))
        newer = mv is not None and (o.as_of is None or mv.at > o.as_of)
        if newer and mv.action == "add":
            rostered_names.add(names.get(o.player_id, ""))
            rostered_count += 1
            changed += o.kind != "team"
            continue
        if newer and mv.action == "drop":
            changed += 1
            pool.append(PoolPlayer(o.player_id, o.player_id, nba, "page", "W", waiver_end(mv.at), o.as_of,
                                   f"Dropped by {mv.team_name}" if mv.team_name else "Dropped"))
            continue
        if o.kind == "team":
            rostered_names.add(names.get(o.player_id, ""))
            rostered_count += 1
        elif o.kind in ("FA", "W"):
            pool.append(PoolPlayer(o.player_id, o.player_id, nba, "page", o.kind, o.waiver_until, o.as_of))

    played = set(db.scalars(select(GameLog.player_id).distinct()))
    nba_count = 0
    if rostered_count:  # without any roster data everyone would look available
        for p in db.scalars(select(NbaPlayer).where(NbaPlayer.id.in_(played))):
            n = norm_name(p.name)
            if p.id in known_nba or n in rostered_names:
                continue
            mv = moves.get(n)
            if mv and mv.action == "add":
                continue  # picked up recently: on someone's roster now
            if mv and mv.action == "drop":
                changed += 1
                pool.append(PoolPlayer(virtual_id(p.id), None, p.id, "nba", "W", waiver_end(mv.at), None,
                                       f"Dropped by {mv.team_name}" if mv.team_name else "Dropped"))
            else:
                pool.append(PoolPlayer(virtual_id(p.id), None, p.id, "nba", "?", None, None))
            nba_count += 1

    page_times = [o.as_of for o in own if o.kind in ("FA", "W") and o.as_of]
    team_times = [o.as_of for o in own if o.kind == "team" and o.as_of]
    info = PoolInfo(
        page_count=len(pool) - nba_count,
        nba_count=nba_count,
        available_as_of=max(page_times) if page_times else None,
        rostered_as_of=min(team_times) if team_times else None,
        rostered_count=rostered_count,
        from_transactions=changed,
    )
    return pool, info
