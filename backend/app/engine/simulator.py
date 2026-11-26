"""Matchup simulator: projected final scores and win probability for the current week.

Starts from the imported score (the Matchup page), then adds every game that hadn't
started when that page was saved:
- On the day the page was saved, the lineup is the one on the page.
- On later days, each team is assumed to set its best lineup (lineup optimizer),
  chosen before the games from projections.
- Games that have finished since then count with their real box-score points.
- Games still to come are simulated many times: each started player plays with his
  chance of playing and scores around his projection (normal spread, floored at 0).

Limitations (shown in the app):
- Games already in progress when the page was saved count only what was scored by then.
- Rosters are as last imported; future adds/drops aren't known.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GameLog, League, Matchup, PlayerMap, RosterSlot
from app.engine.lineup import INACTIVE_SLOTS, Candidate, active_slots, optimize_day
from app.engine.projections import Projection, project_players
from app.engine.schedule import Schedule, date_range, today_et
from app.engine.scoring import fantasy_points, league_weights

SIMULATIONS = 10_000


@dataclass
class DayPlan:
    date: str
    lineup: dict[int, str]  # player_id -> slot (players whose game counts)
    expected: float  # actual points of finished games + expected points of the rest
    actual: float  # points already scored in finished games
    pending: list[int]  # started players whose game hasn't finished
    bench_with_game: list[int]
    from_page: bool  # lineup taken from the imported page instead of optimized


@dataclass
class TeamOutlook:
    team_id: int
    current: float
    remaining_expected: float
    final_expected: float
    final_p10: float
    final_p90: float
    games_left: int
    days: list[DayPlan] = field(default_factory=list)


@dataclass
class MatchupOutlook:
    week: int
    start_date: str
    end_date: str
    as_of: datetime | None
    me: TeamOutlook
    opp: TeamOutlook
    win_prob: float
    projections: dict[int, Projection]
    notes: list[str]
    sim_stats: dict[str, tuple[float, float]] = field(default_factory=dict)  # side -> (mean, variance) of final score
    sims: dict[str, np.ndarray] = field(default_factory=dict, repr=False)  # side -> simulated final scores


def _roster(db: Session, league_id: int, team_id: int) -> dict[int, RosterSlot]:
    rows = {
        r.player_id: r
        for r in db.scalars(select(RosterSlot).where(RosterSlot.league_id == league_id, RosterSlot.team_id == team_id))
    }
    if rows:
        return rows
    # No roster page saved for this team: use its players from the Taken lists (slots unknown -> optimizer every day)
    from app.engine.rosters import team_rosters

    league = db.get(League, league_id)
    ids = team_rosters(db, league)[0].get(team_id, set()) if league else set()
    return {pid: RosterSlot(league_id=league_id, team_id=team_id, player_id=pid, slot="BN") for pid in ids}


def plan_days(
    proj: dict[int, Projection],
    roster: dict[int, RosterSlot],
    slots: list[str],
    sched: Schedule,
    days: list[date],
    snapshot: datetime | None,
    actual_fp: dict[tuple[int, str], float],
    page_ok: bool = True,
) -> list[DayPlan]:
    """page_ok=False: always optimize (the roster differs from the imported page, e.g. after a suggested move)."""
    snap_day = today_et(snapshot) if snapshot else None
    plans = []
    for d in days:
        # Players whose game that day hadn't started when the score was saved
        open_games = {}
        for pid in roster:
            p = proj.get(pid)
            g = sched.game(p.nba_team, d) if p else None
            if g is None or (snapshot and g.start_utc and g.start_utc <= snapshot):
                continue
            open_games[pid] = g

        use_page = page_ok and d == snap_day and any(r.as_of and today_et(r.as_of) == snap_day for r in roster.values())
        if use_page:
            lineup = {pid: r.slot for pid, r in roster.items() if r.slot not in INACTIVE_SLOTS and pid in open_games}
            bench = [pid for pid in open_games if pid not in lineup and proj[pid].play_prob > 0]
        else:
            cands = [
                Candidate(pid, proj[pid].positions, proj[pid].play_prob_on(sched.is_back_to_back(proj[pid].nba_team, d), d) * proj[pid].fpts)
                for pid in open_games
            ]
            lu = optimize_day(slots, cands)
            lineup, bench = lu.assignments, lu.bench_with_game

        actual = 0.0
        pending: list[int] = []
        expected = 0.0
        for pid in lineup:
            g = open_games[pid]
            if g.status == 3:
                pts = actual_fp.get((pid, g.id), 0.0)  # no box score line = didn't play
                actual += pts
                expected += pts
            else:
                pending.append(pid)
                p = proj[pid]
                expected += p.play_prob_on(sched.is_back_to_back(p.nba_team, d), d) * p.fpts
        plans.append(DayPlan(d.isoformat(), lineup, round(expected, 2), round(actual, 2), pending, bench, use_page))
    return plans


def _simulate(plans: list[DayPlan], proj: dict[int, Projection], sched: Schedule, rng: np.random.Generator) -> np.ndarray:
    total = np.zeros(SIMULATIONS)
    for plan in plans:
        total += plan.actual
        d = date.fromisoformat(plan.date)
        for pid in plan.pending:
            p = proj[pid]
            prob = p.play_prob_on(sched.is_back_to_back(p.nba_team, d), d)
            plays = rng.random(SIMULATIONS) < prob
            pts = np.maximum(rng.normal(p.fpts, p.sd, SIMULATIONS), 0.0)
            total += plays * pts
    return total


def _actual_points(db: Session, league: League, yahoo_ids: list[int], start: date, end: date) -> dict[tuple[int, str], float]:
    weights, _ = league_weights(league)
    nba_of = {m.yahoo_id: m.nba_id for m in db.scalars(select(PlayerMap).where(PlayerMap.yahoo_id.in_(yahoo_ids))) if m.nba_id}
    yahoo_of = {v: k for k, v in nba_of.items()}
    logs = db.scalars(
        select(GameLog).where(
            GameLog.player_id.in_(list(nba_of.values())),
            GameLog.date_et >= start.isoformat(),
            GameLog.date_et <= end.isoformat(),
        )
    )
    return {(yahoo_of[g.player_id], g.game_id): fantasy_points(g, weights) for g in logs}


@dataclass
class RosterMove:
    """From `day` on, `add` is on the roster instead of `drop` (None: an empty spot is used)."""

    day: date
    add: int
    drop: int | None


def matchup_outlook(db: Session, league: League, team_id: int, now_utc: datetime | None = None, seed: int = 7,
                    moves: list[RosterMove] | None = None, extra_proj: dict[int, Projection] | None = None) -> MatchupOutlook | None:
    """This week's projected finals and chance to win; `moves` tries roster changes on my side."""
    mu = db.scalar(
        select(Matchup).where(Matchup.league_id == league.id, Matchup.team_id == team_id).order_by(Matchup.week.desc()).limit(1)
    )
    if mu is None or not mu.start_date or not mu.end_date:
        return None
    settings = json.loads(league.settings_json) if league.settings_json else {}
    slots = active_slots(settings.get("roster_positions"))
    start, end = date.fromisoformat(mu.start_date), date.fromisoformat(mu.end_date)
    today = today_et(now_utc)
    snapshot_day = today_et(mu.as_of) if mu.as_of else start
    first_day = max(start, snapshot_day)
    days = date_range(first_day, end) if first_day <= end else []

    sched = Schedule(db, start - timedelta(days=1), end)  # day before: back-to-back on the first day
    my_roster = _roster(db, league.id, team_id)
    opp_roster = _roster(db, league.id, mu.opp_team_id)
    ids = list(my_roster) + list(opp_roster)
    proj = project_players(db, league, ids, today)
    if extra_proj:
        proj.update(extra_proj)
    actual = _actual_points(db, league, ids, start, end)

    if moves:
        my_days = []
        for d in days:
            roster_d = dict(my_roster)
            for m in moves:
                if d >= m.day:
                    if m.drop is not None:
                        roster_d.pop(m.drop, None)
                    roster_d[m.add] = RosterSlot(league_id=league.id, team_id=team_id, player_id=m.add, slot="BN")
            my_days += plan_days(proj, roster_d, slots, sched, [d], mu.as_of, actual, page_ok=roster_d.keys() == my_roster.keys())
    else:
        my_days = plan_days(proj, my_roster, slots, sched, days, mu.as_of, actual)
    opp_days = plan_days(proj, opp_roster, slots, sched, days, mu.as_of, actual)
    # Separate random streams per side: trying a move on my side leaves the opponent's draws unchanged.
    my_sim = (mu.score or 0) + _simulate(my_days, proj, sched, np.random.default_rng(seed))
    opp_sim = (mu.opp_score or 0) + _simulate(opp_days, proj, sched, np.random.default_rng(seed + 1))
    win = float(np.mean(my_sim > opp_sim) + 0.5 * np.mean(my_sim == opp_sim))

    def outlook(tid: int, current: float | None, plans: list[DayPlan], sims: np.ndarray) -> TeamOutlook:
        rem = sum(p.expected for p in plans)
        return TeamOutlook(
            team_id=tid,
            current=current or 0.0,
            remaining_expected=round(rem, 1),
            final_expected=round((current or 0) + rem, 1),
            final_p10=round(float(np.percentile(sims, 10)), 1),
            final_p90=round(float(np.percentile(sims, 90)), 1),
            games_left=sum(len(p.pending) for p in plans),
            days=plans,
        )

    notes = []
    if not settings:
        notes.append("League settings not imported: using default lineup slots and scoring.")
    finished = sum(1 for plans in (my_days, opp_days) for p in plans for pid in p.lineup if pid not in p.pending)
    if finished:
        notes.append(
            f"{finished} player-games finished after the Matchup page was saved; they're counted with real box scores, "
            "assuming the lineups shown. Import a fresh Matchup page for Yahoo's exact score."
        )
    unknown = sorted({proj[pid].name for pid in ids if pid in proj and proj[pid].source == "none"})
    if unknown:
        notes.append(f"No stats found for: {', '.join(unknown)} (projected 0).")

    return MatchupOutlook(
        week=mu.week,
        start_date=mu.start_date,
        end_date=mu.end_date,
        as_of=mu.as_of,
        me=outlook(team_id, mu.score, my_days, my_sim),
        opp=outlook(mu.opp_team_id, mu.opp_score, opp_days, opp_sim),
        win_prob=round(win, 3),
        projections=proj,
        notes=notes,
        sim_stats={"me": (float(my_sim.mean()), float(my_sim.var())), "opp": (float(opp_sim.mean()), float(opp_sim.var()))},
        sims={"me": my_sim, "opp": opp_sim},
    )
