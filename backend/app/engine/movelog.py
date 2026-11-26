"""Move log: suggested moves you opened on Yahoo, and whether they happened.

A move is logged when you click its Yahoo link. Every later import is evidence:
- done:     the player is on your saved roster, or a transaction shows your team adding him
- missed:   another team picked him up first
- not done: your roster was saved more than a day later without him
Imported transactions are matched by name; roster pages by Yahoo id or name.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FantasyTeam, League, MoveLog, Ownership, Player, RosterSlot, Transaction
from app.engine.adds import parse_moves, transaction_time, yahoo_zone
from app.engine.schedule import today_et
from app.nba.matching import norm_name

NOT_DONE_AFTER = timedelta(days=1)


def log_move(db: Session, league: League, team_id: int, *, source: str, add_name: str, add_yahoo_id: int | None = None,
             add_nba_id: int | None = None, drop_yahoo_id: int | None = None, drop_name: str | None = None,
             gain: float | None = None, horizon: str | None = None, now: datetime | None = None) -> MoveLog:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    # Clicking the same move again within a day doesn't add a second entry
    recent = db.scalars(select(MoveLog).where(
        MoveLog.league_id == league.id, MoveLog.team_id == team_id, MoveLog.status == "open",
        MoveLog.add_name == add_name, MoveLog.created_at >= now - timedelta(days=1))).first()
    row = recent or MoveLog(league_id=league.id, team_id=team_id, add_name=add_name, status="open")
    row.created_at = now
    row.source, row.horizon, row.gain = source, horizon, gain
    row.add_yahoo_id, row.add_nba_id = add_yahoo_id, add_nba_id
    row.drop_yahoo_id, row.drop_name = drop_yahoo_id, drop_name
    db.add(row)
    db.commit()
    return row


def _transactions(db: Session, league: League) -> list[tuple[datetime, str | None, str, str]]:
    """[(time UTC, team name, player name (normalised), "add" | "drop")]."""
    zone = yahoo_zone(league)
    out = []
    for t in db.scalars(select(Transaction).where(Transaction.league_id == league.id)):
        at = transaction_time(t.when_text, zone, (t.as_of or datetime.now(UTC)).date())
        if at is None:
            continue
        at_utc = at.astimezone(UTC).replace(tzinfo=None)
        for name, action in parse_moves(t.description):
            out.append((at_utc, t.team_name, norm_name(name), action))
    return out


def resolve(db: Session, league: League, team_id: int, now: datetime | None = None) -> None:
    """Update open moves from the latest imports."""
    now = now or datetime.now(UTC).replace(tzinfo=None)
    open_moves = db.scalars(select(MoveLog).where(MoveLog.league_id == league.id, MoveLog.team_id == team_id,
                                                  MoveLog.status == "open")).all()
    if not open_moves:
        return
    my_name = (db.get(FantasyTeam, (league.id, team_id)) or FantasyTeam()).name
    roster = db.scalars(select(RosterSlot).where(RosterSlot.league_id == league.id, RosterSlot.team_id == team_id)).all()
    roster_ids = {r.player_id for r in roster}
    roster_names = {norm_name(p.name) for p in db.scalars(select(Player).where(Player.id.in_(roster_ids)))}
    roster_at = max((r.as_of for r in roster if r.as_of), default=None)
    txs = _transactions(db, league)

    for m in open_moves:
        name = norm_name(m.add_name)
        on_roster = (m.add_yahoo_id in roster_ids) or name in roster_names
        my_add = next((t for t in txs if t[0] >= m.created_at - timedelta(minutes=5) and t[2] == name
                       and t[3] == "add" and t[1] == my_name), None)
        other_add = next((t for t in txs if t[0] >= m.created_at - timedelta(minutes=5) and t[2] == name
                          and t[3] == "add" and t[1] != my_name), None)
        owner = db.get(Ownership, (league.id, m.add_yahoo_id)) if m.add_yahoo_id else None
        if my_add or (on_roster and roster_at and roster_at >= m.created_at):
            m.status, m.resolved_at = "done", now
            m.note = f"Added {my_add[0]:%b %d} (transactions)" if my_add else "On your saved roster"
        elif other_add or (owner and owner.kind == "team" and owner.team_id != team_id and owner.as_of
                           and owner.as_of >= m.created_at):
            m.status, m.resolved_at = "missed", now
            m.note = f"Picked up by {other_add[1]}" if other_add and other_add[1] else "Picked up by another team"
        elif roster_at and roster_at >= m.created_at + NOT_DONE_AFTER:
            m.status, m.resolved_at = "not done", now
            m.note = "Not on your roster saved since"
    db.commit()


def performance(db: Session, league: League, moves: list[MoveLog]) -> dict:
    """For moves that happened: fantasy points the added player has scored since, vs the player dropped."""
    from app.db.models import GameLog, PlayerMap
    from app.engine.scoring import fantasy_points, league_weights

    weights, _ = league_weights(league)
    out: dict[int, dict] = {}
    total = 0.0
    for m in moves:
        if m.status != "done":
            continue
        since = today_et(m.created_at).isoformat()

        def fp_since(yahoo_id: int | None, nba_id: int | None) -> tuple[float, int] | None:
            nid = nba_id
            if nid is None and yahoo_id:
                pm = db.get(PlayerMap, yahoo_id)
                nid = pm.nba_id if pm else None
            if nid is None:
                return None
            games = db.scalars(select(GameLog).where(GameLog.player_id == nid, GameLog.date_et >= since)).all()
            return sum(fantasy_points(g, weights) for g in games), len(games)

        added = fp_since(m.add_yahoo_id, m.add_nba_id)
        dropped = fp_since(m.drop_yahoo_id, None) if m.drop_yahoo_id else (0.0, 0)
        if added is None or dropped is None:
            continue
        net = added[0] - dropped[0]
        total += net
        out[m.id] = {"added_fp": round(added[0], 1), "added_games": added[1], "dropped_fp": round(dropped[0], 1),
                     "dropped_games": dropped[1], "net": round(net, 1)}
    return {"by_move": out, "total_net": round(total, 1), "moves_counted": len(out)}


def my_transactions(db: Session, league: League, team_id: int) -> list[dict]:
    team = db.get(FantasyTeam, (league.id, team_id))
    if team is None or not team.name:
        return []
    zone = yahoo_zone(league)
    rows = db.scalars(select(Transaction).where(Transaction.league_id == league.id, Transaction.team_name == team.name)).all()

    def when(t: Transaction) -> datetime:
        at = transaction_time(t.when_text, zone, (t.as_of or datetime.now(UTC)).date())
        return at.astimezone(UTC).replace(tzinfo=None) if at else datetime.min

    return [
        {"when": t.when_text, "description": t.description,
         "moves": [{"name": n, "action": a} for n, a in parse_moves(t.description)]}
        for t in sorted(rows, key=when, reverse=True)
    ]
