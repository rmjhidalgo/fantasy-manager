"""Trade analyzer and trade finder.

Analyzer: for a proposed trade, how many points each team's daily lineups gain or lose
over a horizon (A this week, B next week, C next 5 weeks, D playoffs):
- the trade takes effect after the league's review period ("Trade Reject Time", 2 days),
- a team receiving more players than it sends drops its lowest-value players to fit,
- lineup fit counts: a player only helps on days he'd actually start.

Finder: 1-for-1 trades with every other team where *both* sides gain, so the other
manager has a reason to accept. Players of similar value are paired; untouchables are
never offered.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import League
from app.engine.lineup import active_slots
from app.engine.lineup_value import LineupValue
from app.engine.projections import Projection, project_players
from app.engine.rosters import team_names, team_rosters
from app.engine.schedule import Schedule, today_et
from app.engine.suggest import LONG_OUT, adjust_for_horizon, horizon_for
from app.engine.untouchables import get_untouchables

NOT_ON_ROSTER_SLOTS = {"IL", "IL+", "NA"}
FINDER_VALUE_RATIO = (0.8, 1.25)  # pair players whose value over the horizon is within this ratio
FINDER_MIN_GAIN = 3.0  # points each side must gain


def trade_delay_days(league: League) -> int:
    raw = (json.loads(league.settings_json) if league.settings_json else {}).get("raw", {})
    m = re.search(r"(\d+)", raw.get("Trade Reject Time") or "")
    return int(m.group(1)) if m else 2


def trade_deadline(league: League) -> str | None:
    return (json.loads(league.settings_json) if league.settings_json else {}).get("trade_end_date")


@dataclass
class TradeWorld:
    """Everything needed to value rosters over a horizon."""

    league: League
    key: str
    label: str
    days: list[date]
    start: int | None  # day index when a trade made today takes effect
    effective: date
    slots: list[str]
    capacity: int
    il_slots: int
    rosters: dict[int, set[int]]
    il: dict[int, set[int]]
    names: dict[int, str]
    proj: dict[int, Projection]
    lv: LineupValue
    deadline: str | None
    notes: list[str]

    def active(self, team: int) -> set[int]:
        ids = {p for p in self.rosters.get(team, set()) if p in self.proj}
        if team in self.il:
            return ids - self.il[team]
        # IL slots unknown for this team: assume its long-term injured players fill them
        hurt = sorted((p for p in ids if self.proj[p].status in LONG_OUT), key=lambda p: self.proj[p].fpts)
        return ids - set(hurt[: self.il_slots])

    def value(self, pid: int) -> float:
        """Points he'd score over the horizon from the effective day (ignoring lineup limits)."""
        return sum(self.lv.values(pid)[self.start:]) if self.start is not None else 0.0

    def games(self, pid: int) -> int:
        return self.lv.games(pid, self.start) if self.start is not None else 0


def build_world(db: Session, league: League, my_team: int, key: str = "C", now_utc: datetime | None = None) -> TradeWorld:
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    today = today_et(now)
    hz = horizon_for(db, league, my_team, key, today)
    settings = json.loads(league.settings_json) if league.settings_json else {}
    positions = settings.get("roster_positions") or []
    slots = active_slots(positions)
    rosters, il = team_rosters(db, league)
    all_ids = [p for ids in rosters.values() for p in ids]
    proj = project_players(db, league, all_ids, today)
    adjust_for_horizon(proj, key)
    days = hz.days
    sched = Schedule(db, (days[0] if days else today) - timedelta(days=1), days[-1] if days else today)
    lv = LineupValue(slots, sched, days, proj, now, today)
    effective = today + timedelta(days=trade_delay_days(league))
    start = lv.first_day_index(effective) if days else None
    notes = list(hz.notes)
    deadline = trade_deadline(league)
    if deadline and today.isoformat() > deadline:
        notes.insert(0, f"The trade deadline ({deadline}) has passed.")
    return TradeWorld(league, key, hz.label, days, start, effective, slots,
                      len([s for s in positions if s not in NOT_ON_ROSTER_SLOTS]) or len(slots) + 3,
                      sum(1 for s in positions if s in ("IL", "IL+")), rosters, il, team_names(db, league), proj, lv,
                      deadline, notes)


def _side(w: TradeWorld, team: int, out: list[int], inn: list[int]) -> dict:
    """Points this team's lineups gain over the horizon from the trade (after any drops needed to fit)."""
    before = w.active(team)
    after = (before - set(out)) | set(inn)
    drops: list[int] = []
    while len(after) > w.capacity:
        # Drop the lowest-value player that isn't part of the trade
        cands = sorted((p for p in after if p not in inn), key=w.value) or sorted(after, key=w.value)
        drops.append(cands[0])
        after.discard(cands[0])
    n = len(w.days)
    if w.start is None:
        return {"gain": 0.0, "drops": drops, "before": 0.0, "after": 0.0}
    tl_before = [before for _ in range(n)]
    tl_after = [before if i < w.start else after for i in range(n)]
    b, a = w.lv.total(tl_before), w.lv.total(tl_after)
    return {"gain": round(a - b, 1), "drops": drops, "before": round(b, 1), "after": round(a, 1)}


def _player(w: TradeWorld, pid: int) -> dict:
    p = w.proj[pid]
    return {"id": pid, "name": p.name, "nba_team": p.nba_team, "positions": p.positions, "status": p.status,
            "fpts": p.fpts, "games": w.games(pid), "value": round(w.value(pid), 1)}


def analyze_trade(db: Session, league: League, my_team: int, other_team: int, give: list[int], get: list[int],
                  key: str = "C", now_utc: datetime | None = None, world: TradeWorld | None = None) -> dict:
    w = world or build_world(db, league, my_team, key, now_utc)
    mine, theirs = w.rosters.get(my_team, set()), w.rosters.get(other_team, set())
    bad = [p for p in give if p not in mine] + [p for p in get if p not in theirs]
    if not give or not get:
        raise ValueError("Pick at least one player on each side.")
    if bad:
        raise ValueError("Some players aren't on those rosters (as last imported).")
    me = _side(w, my_team, give, get)
    them = _side(w, other_team, get, give)
    verdict = ("Good for both teams" if me["gain"] > 0 and them["gain"] > 0 else
               "Good for you" if me["gain"] > 0 else "Good for them" if them["gain"] > 0 else "Bad for both")
    return {
        "horizon": key, "label": w.label, "days": [w.days[0].isoformat(), w.days[-1].isoformat()] if w.days else [],
        "effective": w.effective.isoformat(), "deadline": w.deadline,
        "my_team": {"id": my_team, "name": w.names.get(my_team), **me, "drops": [_player(w, p) for p in me["drops"]]},
        "their_team": {"id": other_team, "name": w.names.get(other_team), **them, "drops": [_player(w, p) for p in them["drops"]]},
        "give": [_player(w, p) for p in give],
        "get": [_player(w, p) for p in get],
        "verdict": verdict,
        "notes": w.notes + ([] if w.start is not None else ["The trade would only take effect after this horizon ends."]),
    }


def find_trades(db: Session, league: League, my_team: int, key: str = "C", now_utc: datetime | None = None,
                limit: int = 10) -> dict:
    w = build_world(db, league, my_team, key, now_utc)
    untouchable = get_untouchables(db, league.id, my_team)
    result = {"horizon": key, "label": w.label, "effective": w.effective.isoformat(), "deadline": w.deadline,
              "notes": w.notes, "trades": []}
    if w.start is None:
        return result
    n = len(w.days)
    my_active = w.active(my_team)
    my_base = [w.lv.day_total(i, my_active) for i in range(n)]
    base_cache: dict[int, list[float]] = {}

    def gain(team: int, active: set[int], base: list[float], out: int, inn: int) -> float:
        after = (active - {out}) | {inn}
        return sum(w.lv.day_total(i, after) - base[i] for i in range(w.start, n)
                   if w.lv.values(out)[i] > 0 or w.lv.values(inn)[i] > 0)

    found = []
    lo, hi = FINDER_VALUE_RATIO
    for team, ids in w.rosters.items():
        if team == my_team:
            continue
        their_active = w.active(team)
        for a in my_active - untouchable:
            va = w.value(a)
            if va <= 0:
                continue
            for b in their_active:
                vb = w.value(b)
                if vb <= 0 or not lo <= vb / va <= hi:
                    continue
                g_me = gain(my_team, my_active, my_base, a, b)
                if g_me < FINDER_MIN_GAIN:
                    continue
                if team not in base_cache:
                    base_cache[team] = [w.lv.day_total(i, their_active) for i in range(n)]
                g_them = gain(team, their_active, base_cache[team], b, a)
                if g_them < FINDER_MIN_GAIN:
                    continue
                found.append((min(g_me, g_them), g_me, g_them, team, a, b))
    found.sort(reverse=True)
    seen: set[tuple[int, int]] = set()
    for _, g_me, g_them, team, a, b in found:
        if (a, team) in seen:  # one idea per player per team
            continue
        seen.add((a, team))
        result["trades"].append({
            "team": {"id": team, "name": w.names.get(team)},
            "give": _player(w, a), "get": _player(w, b),
            "my_gain": round(g_me, 1), "their_gain": round(g_them, 1),
        })
        if len(result["trades"]) >= limit:
            break
    return result
