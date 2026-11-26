"""Suggested Moves: the add/drops (and IL moves) that most improve your result for a horizon.

Horizons:
  A  this week      today -> end of the current week; aims at your chance to win this matchup
                    (when far ahead it prefers steady players, when behind higher-upside ones)
  B  next week      the next full week; projected points (and chance to win if next week's
                    opponent is known from an imported Matchup page)
  C  next 5 weeks   total projected points over the next 5 weeks (longer-term value)
  D  playoffs       projected points in the playoff weeks, assuming today's injuries have
                    healed by then and weighting season-long form

How it decides (engine math only, no AI):
1. Candidates: the best available players over the horizon, paired with your lowest-value
   droppable players. Untouchables are never dropped.
2. Gain: the lineup optimizer runs over every day of the horizon with and without the move;
   the gain is the change in points that actually end up in your daily lineups.
3. Budget: adds left this week (next week's moves: the weekly limit, as adds reset Monday).
4. Moves are combined greedily into the best set for the budget.
5. Anything below a minimum gain is dropped; with nothing left the answer is "Hold".
"""

import json
import math
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import League, Matchup, RosterSlot
from app.engine.adds import adds_used
from app.engine.freeagents import TeamContext, build_context, current_week
from app.engine.lineup import Candidate, active_slots, optimize_day
from app.engine.lineup_value import LineupValue
from app.engine.projections import Projection, project_players
from app.engine.schedule import Schedule, date_range, today_et
from app.engine.simulator import RosterMove, matchup_outlook
from app.engine.weeks import playoff_weeks, weeks_after
from app.nba import sync

LONG_OUT = {"O", "INJ", "OFS", "SUSP", "NA"}
MIN_GAIN = {"A": 2.0, "B": 2.0, "C": 5.0, "D": 5.0}
CANDIDATES = 40
DROPS = 5
KEEP_TOLERANCE = 1.5  # short horizons: don't drop a player better per game than the pickup by more than this
WIN_STEP = 0.002  # this-week moves: a change in win chance smaller than this counts as no change

HORIZON_NAMES = {"A": "This week", "B": "Next week", "C": "Next 5 weeks", "D": "Playoffs"}


@dataclass
class Horizon:
    key: str
    days: list[date]
    label: str
    weeks: list[tuple[int | None, date, date]] = field(default_factory=list)
    opponent: int | None = None  # B: next week's opponent, if a Matchup page for it was imported
    notes: list[str] = field(default_factory=list)


def horizon_for(db: Session, league: League, team_id: int, key: str, today: date) -> Horizon:
    week, _, end = current_week(db, league, team_id, today)
    if key == "A":
        return Horizon("A", date_range(today, end), f"Rest of week {week}" if week else "Rest of this week",
                       [(week, today, end)])
    if key == "B":
        weeks = weeks_after(week, end, 1)
        w, s, e = weeks[0]
        opp = None
        if w is not None:
            mu = db.scalar(select(Matchup).where(Matchup.league_id == league.id, Matchup.team_id == team_id, Matchup.week == w))
            opp = mu.opp_team_id if mu else None
        notes = [] if opp else ["Next week's opponent isn't known (save next week's Matchup page to see your chance to win)."]
        return Horizon("B", date_range(s, e), f"Week {w}" if w else "Next week", weeks, opp, notes)
    if key == "C":
        weeks = weeks_after(week, end, 5)
        first, last = weeks[0], weeks[-1]
        label = f"Weeks {first[0]}–{last[0]}" if first[0] else "Next 5 weeks"
        return Horizon("C", date_range(first[1], last[2]), label, weeks,
                       notes=["Weeks are counted as Monday–Sunday; a longer Yahoo week (e.g. All-Star break) shifts later dates."])
    if key == "D":
        weeks = playoff_weeks(league, today)
        if not weeks:
            return Horizon("D", [], "Playoffs", [], notes=["Playoff weeks unknown: import the league Settings page."])
        days = [d for _, s, e in weeks for d in date_range(s, e)]
        label = "Playoff weeks " + ", ".join(str(w) for w, _, _ in weeks)
        return Horizon("D", days, label, weeks, notes=[
            "Playoff dates come from the playoff end date on your Settings page.",
            "Assumes today's injuries have healed by then (except out-for-season) and weights season-long form.",
        ])
    raise ValueError(f"Unknown horizon {key}")


def adjust_for_horizon(proj: dict[int, Projection], key: str) -> None:
    """Far-off horizons: today's injury tags matter less, season-long form more."""
    if key not in ("C", "D"):
        return
    for pid, p in list(proj.items()):
        prob = p.play_prob
        if p.status in ("OFS",):
            prob = 0.0
        elif key == "D":
            prob = 0.9
        elif p.status in LONG_OUT:
            prob = 0.6  # some of the 5 weeks
        elif p.status:
            prob = 0.9
        fpts = p.fpts
        season = p.window_fp.get("S")
        if key == "D" and season is not None:
            fpts = round(0.5 * p.fpts + 0.5 * season, 2)
        proj[pid] = replace(p, play_prob=prob, fpts=fpts)


@dataclass
class Move:
    add: int
    drop: int | None
    start: int  # day index the pickup can first play
    gain: float  # FP gain over the horizon (at the time it was chosen)
    win_change: float | None = None
    before: list[set[int]] = field(default_factory=list)  # roster timeline before this move


def _normal_win(my_mean: float, my_var: float, opp_mean: float, opp_var: float) -> float:
    sd = math.sqrt(max(my_var + opp_var, 1e-9))
    return 0.5 * (1 + math.erf((my_mean - opp_mean) / (sd * math.sqrt(2))))


def _game_days(lv: LineupValue, pid: int, start: int) -> list[int]:
    return [i for i in range(start, len(lv.days)) if lv.has_open_game(pid, i)]


def _empty_slot_days(ctx: TeamContext, timeline: list[set[int]], pid: int, drop: int | None, start: int) -> int:
    """Days the move puts one more player in your lineup (a slot that would otherwise stay empty)."""
    def starters(ids: set[int], i: int) -> int:
        cands = [Candidate(p, ctx.proj[p].positions, ctx.lv.values(p)[i]) for p in ids if ctx.lv.values(p)[i] > 0]
        return len(optimize_day(ctx.slots, cands).assignments)

    return sum(1 for i in _game_days(ctx.lv, pid, start)
               if starters((timeline[i] - {drop}) | {pid}, i) > starters(timeline[i], i))


def _reasons(ctx: TeamContext, key: str, m: Move, timeline_before: list[set[int]], pool_kind: str,
             available_from: date) -> list[str]:
    lv, p = ctx.lv, ctx.proj[m.add]
    out = []
    g_add = len(_game_days(lv, m.add, m.start))
    if m.drop is not None:
        d = ctx.proj[m.drop]
        g_drop = len(_game_days(lv, m.drop, m.start))
        out.append(f"Plays {g_add} game{'s' if g_add != 1 else ''} in this window vs {g_drop} for {d.name}.")
        out.append(f"Projects {p.fpts:.1f} FP/G vs {d.fpts:.1f} for {d.name}.")
    else:
        out.append(f"Plays {g_add} game{'s' if g_add != 1 else ''} in this window and uses your empty roster spot (no drop needed).")
        out.append(f"Projects {p.fpts:.1f} FP/G.")
    empty = _empty_slot_days(ctx, timeline_before, m.add, m.drop, m.start)
    if empty and key in ("A", "B"):
        out.append(f"Fills an empty lineup slot on {empty} of those days.")
    if p.recent_mpg is not None and p.season_mpg is not None and p.recent_mpg - p.season_mpg >= 3:
        out.append(f"Minutes up lately: {p.recent_mpg:.0f} per game over 14 days (season {p.season_mpg:.0f}).")
    l14, s = p.window_fp.get("L14"), p.window_fp.get("S")
    if l14 is not None and s is not None and l14 - s >= 3:
        out.append(f"In form: {l14:.1f} FP/G over the last 14 days (season {s:.1f}).")
    if pool_kind == "W":
        when = f"{available_from.strftime('%a %b')} {available_from.day}"
        if available_from > lv.days[0]:
            out.append(f"On waivers: a claim, so he only counts from {when}.")
        else:
            out.append(f"On waivers until {when}: put in a claim.")
    elif pool_kind == "?":
        out.append("Not on a saved page: check on Yahoo that he's a free agent (positions are estimated).")
    if p.status:
        out.append(f"Injury tag {p.status}: counted at {p.play_prob:.0%} to play.")
    if m.drop is not None and ctx.proj[m.drop].status in LONG_OUT and key in ("A", "B"):
        out.append(f"{ctx.proj[m.drop].name} is tagged {ctx.proj[m.drop].status}.")
    return out


def suggest_moves(db: Session, league: League, team_id: int, key: str, now_utc: datetime | None = None,
                  budget: int | None = None) -> dict:
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    today = today_et(now)
    hz = horizon_for(db, league, team_id, key, today)
    week, wstart, wend = current_week(db, league, team_id, today)
    adds = adds_used(db, league, team_id, week, wstart, wend)
    limit = adds["limit"] if adds["limit"] is not None else 3
    if budget is None:
        budget = limit if key == "B" else (adds["left"] if adds["left"] is not None else limit)

    result: dict = {
        "horizon": key,
        "horizon_name": HORIZON_NAMES[key],
        "label": hz.label,
        "days": [d.isoformat() for d in hz.days],
        "weeks": [{"week": w, "start": s.isoformat(), "end": e.isoformat()} for w, s, e in hz.weeks],
        "budget": budget,
        "adds": adds,
        "notes": list(hz.notes),
        "moves": [],
        "il_moves": [],
        "baseline": 0.0,
        "with_moves": 0.0,
        "win_before": None,
        "win_after": None,
        "min_gain": MIN_GAIN[key],
    }
    if not hz.days:
        return result

    ctx = build_context(db, league, team_id, now_utc=now, days=hz.days, label=hz.label)
    adjust_for_horizon(ctx.proj, key)
    lv = ctx.lv
    n = len(hz.days)
    result["untouchable"] = sorted(ctx.untouchable)
    result["warnings"] = _freshness(ctx, now)

    # IL moves first: a long-term injured player on a regular spot, with an IL slot free, opens a spot for free.
    settings = json.loads(league.settings_json) if league.settings_json else {}
    il_free = sum(1 for s in settings.get("roster_positions") or [] if s in ("IL", "IL+")) - sum(
        1 for r in ctx.roster if r.slot in ("IL", "IL+"))
    status_now = {r.player_id: ctx.proj[r.player_id].status for r in ctx.roster if r.player_id in ctx.proj}
    # (He stays in the plan: an IL player can be activated when healthy, which matters for later horizons.)
    for pid in ctx.active_ids:
        if il_free > 0 and status_now.get(pid) in LONG_OUT:
            result["il_moves"].append({"player_id": pid, "name": ctx.proj[pid].name, "status": status_now[pid]})
            il_free -= 1

    timeline = [set(ctx.active_ids) for _ in range(n)]
    baseline_mean, baseline_var = lv.total_stats(timeline)

    # Who could be added, and from which day
    starts: dict[int, int] = {}
    kinds: dict[int, tuple[str, date, object]] = {}
    raw = []
    for pp in ctx.pool:
        if pp.id not in ctx.proj:
            continue
        avail = ctx.available_from(pp)
        s = lv.first_day_index(avail)
        if s is None:
            continue
        starts[pp.id] = s
        kinds[pp.id] = (pp.kind, avail, pp)
        raw.append((sum(lv.values(pp.id)[s:]), pp.id))
    cands = [pid for v, pid in sorted(raw, reverse=True)[:CANDIDATES] if v > 0]

    # Who could be dropped: short horizons by per-game projection; long ones by value over the horizon
    if key in ("A", "B"):
        drop_pool = ctx.droppable(DROPS)
    else:
        horizon_value = {pid: sum(lv.values(pid)) for pid in ctx.active_ids if pid not in ctx.untouchable}
        drop_pool = sorted(horizon_value, key=horizon_value.get)[:DROPS]
    result["drop_candidates"] = [{"id": d, "name": ctx.proj[d].name, "fpts": ctx.proj[d].fpts} for d in drop_pool]

    # This week: chance to win from the simulator, nudged by mean/variance changes while searching
    outlook = matchup_outlook(db, league, team_id, now_utc=now) if key == "A" else None
    opp_stats = None
    if outlook:
        my_mean0, my_var0 = outlook.sim_stats["me"]
        opp_stats = outlook.sim_stats["opp"]
        result["win_before"] = outlook.win_prob
    elif key == "B" and hz.opponent:
        opp_stats = _opponent_stats(db, league, hz.opponent, ctx, now)

    def win_of(mean: float, var: float) -> float | None:
        if opp_stats is None:
            return None
        if outlook:
            return _normal_win(my_mean0 + mean - baseline_mean, my_var0 + var - baseline_var, *opp_stats)
        return _normal_win(mean, var, *opp_stats)

    current_mean, current_var = baseline_mean, baseline_var
    if key == "B" and opp_stats:
        result["win_before"] = round(win_of(baseline_mean, baseline_var), 3)
    roster_spots = ctx.capacity - len(ctx.active_ids) + len(result["il_moves"])
    used_adds: set[int] = set()
    used_drops: set[int] = set()
    moves: list[Move] = []
    for _ in range(budget):
        best = None
        cur_win = win_of(current_mean, current_var)
        for pid in cands:
            if pid in used_adds:
                continue
            s = starts[pid]
            options: list[int | None] = [None] if roster_spots > 0 else [d for d in drop_pool if d not in used_drops]
            for drop in options:
                if (drop is not None and key in ("A", "B")
                        and ctx.proj[pid].fpts < ctx.proj[drop].fpts - KEEP_TOLERANCE):
                    continue
                tl = [t if i < s else (t - {drop}) | {pid} for i, t in enumerate(timeline)]
                mean, var = lv.total_stats(tl)
                gain = mean - current_mean
                w = win_of(mean, var)
                dw = (w - cur_win) if w is not None and cur_win is not None else None
                # rank: chance to win first when it moves noticeably, else points
                score = (round(dw / WIN_STEP) if dw is not None else 0, gain)
                if best is None or score > best[0]:
                    best = (score, pid, drop, s, tl, mean, var, gain, dw)
        if best is None:
            break
        _, pid, drop, s, tl, mean, var, gain, dw = best
        if gain < MIN_GAIN[key] and not (dw is not None and dw >= 0.01):
            break
        moves.append(Move(pid, drop, s, round(gain, 1), round(dw, 3) if dw is not None else None, before=timeline))
        used_adds.add(pid)
        if drop is None:
            roster_spots -= 1
        else:
            used_drops.add(drop)
        timeline = tl
        current_mean, current_var = mean, var

    # Real simulation of the final set for this week
    if key == "A" and moves:
        extra = {m.add: ctx.proj[m.add] for m in moves}
        after = matchup_outlook(db, league, team_id, now_utc=now, extra_proj=extra,
                                moves=[RosterMove(hz.days[m.start], m.add, m.drop) for m in moves])
        result["win_after"] = after.win_prob if after else None
    elif key == "B" and opp_stats:
        result["win_after"] = round(win_of(current_mean, current_var), 3)

    result["baseline"] = round(baseline_mean, 1)
    result["with_moves"] = round(current_mean, 1)
    for m in moves:
        kind, avail, pp = kinds[m.add]
        p = ctx.proj[m.add]
        result["moves"].append({
            "add": {
                "id": m.add, "yahoo_id": pp.yahoo_id, "name": p.name, "nba_team": p.nba_team, "positions": p.positions,
                "positions_estimated": p.positions_estimated, "status": p.status, "fpts": p.fpts, "kind": kind,
                "source": pp.source,
            },
            "drop": m.drop and {"id": m.drop, "name": ctx.proj[m.drop].name, "fpts": ctx.proj[m.drop].fpts,
                                "status": ctx.proj[m.drop].status},
            "type": "waiver claim" if kind == "W" else "add/drop" if m.drop else "add",
            "first_day": hz.days[m.start].isoformat(),
            "games": len(_game_days(lv, m.add, m.start)),
            "games_dropped": len(_game_days(lv, m.drop, m.start)) if m.drop else 0,
            "gain": m.gain,
            "win_change": m.win_change,
            "reasons": _reasons(ctx, key, m, m.before, kind, avail),
        })
    if key == "A" and outlook and outlook.win_prob >= 0.95:
        result["notes"].append("You're a big favourite this week: the moves above add points, but check horizon C before "
                               "spending adds on short-term streams.")
    return result


def _opponent_stats(db: Session, league: League, opp_id: int, ctx: TeamContext, now: datetime) -> tuple[float, float]:
    roster = db.scalars(select(RosterSlot).where(RosterSlot.league_id == league.id, RosterSlot.team_id == opp_id)).all()
    proj = project_players(db, league, [r.player_id for r in roster], ctx.today)
    ids = {r.player_id for r in roster if r.slot not in ("IL", "IL+", "NA") and r.player_id in proj}
    settings = json.loads(league.settings_json) if league.settings_json else {}
    sched = Schedule(db, ctx.days[0] - timedelta(days=1), ctx.days[-1])
    lv = LineupValue(active_slots(settings.get("roster_positions")), sched, ctx.days, proj, now, ctx.today)
    return lv.total_stats([ids for _ in ctx.days])


def _freshness(ctx: TeamContext, now: datetime) -> list[str]:
    def age(t: datetime | None) -> float | None:
        return (now - t).total_seconds() / 3600 if t else None

    out = []
    roster_t = max((r.as_of for r in ctx.roster if r.as_of), default=None)
    a = age(roster_t)
    if a is None or a > 24:
        out.append("Your roster was last imported " + (f"{a / 24:.1f} days ago" if a else "never") + ": re-save your Team page.")
    a = age(ctx.pool_info.available_as_of)
    if a is not None and a > 48:
        out.append(f"Free agents last imported {a / 24:.1f} days ago, so some may be taken.")
    a = age(ctx.pool_info.rostered_as_of)
    if a is not None and a > 72:
        out.append(f"Taken players last imported {a / 24:.1f} days ago: some 'available' players may have been picked up.")
    r = sync.refreshed_at()
    a = age(r)
    if a is None or a > 6:
        out.append("NBA data is out of date: refresh it on the Import & data tab.")
    return out
