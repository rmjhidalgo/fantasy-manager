"""Free agent finder: rank available players by the points they'd add to *your* lineup.

For each candidate, over the chosen days:
- gain = (points your best daily lineups score with him, minus the player you'd drop)
         - (points they score with your roster as it is)
- a free agent can play from today (league setting "Daily - Today"); a waiver player
  from the day his waiver period ends.
- the drop is chosen among your lowest-projected players (never your stars just because
  they have fewer games this week). With an empty roster spot, nobody needs to go.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import League, Matchup, PlayerStats, RosterSlot
from app.engine.lineup import active_slots
from app.engine.lineup_value import LineupValue
from app.engine.pool import PoolInfo, PoolPlayer, available_pool
from app.engine.projections import Projection, project_nba_players, project_players
from app.engine.schedule import Schedule, date_range, today_et
from app.engine.untouchables import get_untouchables

NOT_ON_ROSTER_SLOTS = {"IL", "IL+", "NA"}  # these slots don't use a regular roster spot
DROP_CANDIDATES = 4  # consider dropping only your lowest-projected players
EVALUATE = 60  # candidates evaluated in full (best by raw points over the days)


@dataclass
class TeamContext:
    league: League
    team_id: int
    today: date
    now: datetime
    days: list[date]
    window_label: str
    slots: list[str]
    capacity: int  # regular roster spots (active + bench)
    roster: list[RosterSlot]
    active_ids: list[int]  # players taking a regular roster spot
    proj: dict[int, Projection]
    pool: list[PoolPlayer]
    pool_info: PoolInfo
    lv: LineupValue
    untouchable: set[int]

    @property
    def open_spots(self) -> int:
        return max(0, self.capacity - len(self.active_ids))

    def droppable(self, n: int = DROP_CANDIDATES) -> list[int]:
        """Your lowest-projected players (per game), never an untouchable."""
        ranked = sorted((p for p in self.active_ids if p not in self.untouchable), key=lambda pid: self.proj[pid].fpts)
        return ranked[:n]

    def available_from(self, pp: PoolPlayer) -> date:
        if pp.kind == "W" and pp.waiver_until:
            return max(self.today, date.fromisoformat(pp.waiver_until))
        return self.today


def current_week(db: Session, league: League, team_id: int, today: date) -> tuple[int | None, date, date]:
    """The matchup week containing today (from the imported matchup), else Monday-Sunday of this week."""
    for mu in db.scalars(select(Matchup).where(Matchup.league_id == league.id, Matchup.team_id == team_id).order_by(Matchup.week.desc())):
        if mu.start_date and mu.end_date and mu.start_date <= today.isoformat() <= mu.end_date:
            return mu.week, date.fromisoformat(mu.start_date), date.fromisoformat(mu.end_date)
    monday = today - timedelta(days=today.weekday())
    return None, monday, monday + timedelta(days=6)


def window_days(db: Session, league: League, team_id: int, window: str, today: date) -> tuple[list[date], str]:
    if window == "week":
        week, _, end = current_week(db, league, team_id, today)
        return date_range(today, end), f"Rest of week {week}" if week else "Rest of this week"
    n = int(window)
    return date_range(today, today + timedelta(days=n - 1)), f"Next {n} days"


def build_context(db: Session, league: League, team_id: int, window: str = "week", now_utc: datetime | None = None,
                  days: list[date] | None = None, label: str | None = None) -> TeamContext:
    """Everything needed to value roster moves over some days (a named window, or the given days)."""
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    today = today_et(now)
    if days is None:
        days, label = window_days(db, league, team_id, window, today)
    settings = json.loads(league.settings_json) if league.settings_json else {}
    positions = settings.get("roster_positions") or []
    slots = active_slots(positions)
    capacity = len([s for s in positions if s not in NOT_ON_ROSTER_SLOTS]) or len(slots) + 3
    roster = db.scalars(select(RosterSlot).where(RosterSlot.league_id == league.id, RosterSlot.team_id == team_id)).all()
    pool, info = available_pool(db, league)
    yahoo_ids = [r.player_id for r in roster] + [p.yahoo_id for p in pool if p.yahoo_id]
    proj = project_players(db, league, yahoo_ids, today)
    proj.update(project_nba_players(db, league, [p.nba_id for p in pool if p.source == "nba" and p.nba_id], today))
    sched = Schedule(db, days[0] - timedelta(days=1), days[-1]) if days else Schedule(db, today, today)
    active = [r.player_id for r in roster if r.slot not in NOT_ON_ROSTER_SLOTS and r.player_id in proj]
    return TeamContext(league, team_id, today, now, days, label or "", slots, capacity, list(roster), active, proj, pool, info,
                       LineupValue(slots, sched, days, proj, now, today), get_untouchables(db, league.id, team_id))


def best_add(ctx: TeamContext, pid: int, start: int, base_timeline: list[set[int]], drops: list[int],
             open_spot: bool) -> tuple[float, int | None]:
    """Best gain from adding pid from day index start, and who to drop (None = use an empty spot)."""
    lv = ctx.lv
    base = lv.total(base_timeline)
    options: list[int | None] = [None] if open_spot else list(drops)
    best_gain, best_drop = float("-inf"), None
    for drop in options:
        tl = [s if i < start else (s - {drop}) | {pid} for i, s in enumerate(base_timeline)]
        gain = lv.total(tl) - base
        if gain > best_gain:
            best_gain, best_drop = gain, drop
    return best_gain, best_drop


def rank_free_agents(db: Session, league: League, team_id: int, window: str = "week", position: str | None = None,
                     now_utc: datetime | None = None) -> dict:
    ctx = build_context(db, league, team_id, window, now_utc)
    lv = ctx.lv
    n = len(ctx.days)
    base_tl = [set(ctx.active_ids) for _ in range(n)]
    drops = ctx.droppable()
    stats = {
        s.player_id: s for s in db.scalars(select(PlayerStats).where(PlayerStats.league_id == league.id))
        if s.window.startswith("S_AS")
    }

    scored = []
    for pp in ctx.pool:
        p = ctx.proj.get(pp.id)
        if p is None or (position and position not in p.positions):
            continue
        start = lv.first_day_index(ctx.available_from(pp))
        raw = sum(lv.values(pp.id)[start:]) if start is not None else 0.0
        scored.append((raw, pp, p, start))
    scored.sort(key=lambda x: (-x[0], -x[2].fpts))

    rows = []
    for k, (raw, pp, p, start) in enumerate(scored):
        gain, drop = None, None
        if k < EVALUATE and start is not None and n:
            gain, drop = best_add(ctx, pp.id, start, base_tl, drops, ctx.open_spots > 0)
        ys = stats.get(pp.yahoo_id) if pp.yahoo_id else None
        rows.append({
            "id": pp.id,
            "yahoo_id": pp.yahoo_id,
            "name": p.name,
            "nba_team": p.nba_team,
            "positions": p.positions,
            "positions_estimated": p.positions_estimated,
            "status": p.status,
            "missed_streak": p.missed_streak,
            "kind": pp.kind,
            "source": pp.source,
            "waiver_until": pp.waiver_until,
            "available_from": ctx.available_from(pp).isoformat(),
            "fpts": p.fpts,
            "play_prob": p.play_prob,
            "window_fp": p.window_fp,
            "recent_mpg": p.recent_mpg,
            "season_mpg": p.season_mpg,
            "pct_rostered": ys.pct_rostered if ys else None,
            "games": lv.games(pp.id, start) if start is not None else 0,
            "raw_expected": round(raw, 1),
            "gain": round(gain, 1) if gain is not None else None,
            "drop": drop,
            "drop_name": ctx.proj[drop].name if drop else None,
            # per-game difference: below 0 means the drop is the better player for the rest of the season
            "vs_drop": round(p.fpts - ctx.proj[drop].fpts, 1) if drop else None,
            "note": pp.note,
        })
        if k >= EVALUATE * 3:
            break
    rows.sort(key=lambda r: (r["gain"] is None, -(r["gain"] or 0), -r["raw_expected"]))
    return {
        "window": window,
        "window_label": ctx.window_label,
        "days": [d.isoformat() for d in ctx.days],
        "open_spots": ctx.open_spots,
        "drop_candidates": [{"id": d, "name": ctx.proj[d].name, "fpts": ctx.proj[d].fpts} for d in drops],
        "pool": {
            "from_pages": ctx.pool_info.page_count,
            "from_nba": ctx.pool_info.nba_count,
            "available_as_of": ctx.pool_info.available_as_of,
            "rostered_as_of": ctx.pool_info.rostered_as_of,
            "rostered_count": ctx.pool_info.rostered_count,
            "from_transactions": ctx.pool_info.from_transactions,
        },
        "players": rows,
    }
