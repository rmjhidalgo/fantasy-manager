"""Playoff odds: simulate the rest of the regular season thousands of times.

- This week: each matchup is simulated from its current score (all six are on the
  League home page), using the same day-by-day simulator as the Matchup screen.
- Later weeks: each team's weekly score is drawn around its projected average (best
  lineups over the remaining regular-season days, injured players assumed back over time),
  with week-to-week noise and a season-long "form" factor per team.
- Opponents: the real pairing where a Matchup page for that week was saved; otherwise a
  random opponent each week (the full league schedule isn't on a saved page yet).
- Standings: wins, then points for. The top N (from the settings page) make the playoffs.

Also answers "what if": your playoff chance if you win vs lose this week.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FantasyTeam, League, Matchup
from app.engine.freeagents import current_week
from app.engine.lineup import active_slots
from app.engine.lineup_value import LineupValue
from app.engine.projections import project_players
from app.engine.rosters import team_names, team_rosters
from app.engine.schedule import Schedule, date_range, today_et
from app.engine.simulator import matchup_outlook
from app.engine.suggest import LONG_OUT, adjust_for_horizon
from app.engine.weeks import playoff_weeks

SEASONS = 5000
WEEK_NOISE = 0.10  # extra week-to-week spread, as a share of a team's weekly average
FORM_SPREAD = 0.04  # season-long strength uncertainty per team


@dataclass
class TeamWeekly:
    mean: float
    sd: float


def playoff_spots(league: League) -> int:
    raw = (json.loads(league.settings_json) if league.settings_json else {}).get("raw", {})
    m = re.search(r"(\d+)\s*teams", raw.get("Playoffs") or "")
    return int(m.group(1)) if m else 8


def _weekly_strength(db: Session, league: League, rosters: dict[int, set[int]], il: dict[int, set[int]],
                     days: list, weeks_left: int, now: datetime) -> dict[int, TeamWeekly]:
    """Each team's average weekly score (and spread) over the remaining regular-season days."""
    today = today_et(now)
    all_ids = [p for ids in rosters.values() for p in ids]
    proj = project_players(db, league, all_ids, today)
    adjust_for_horizon(proj, "C")  # injured players gradually return
    settings = json.loads(league.settings_json) if league.settings_json else {}
    positions = settings.get("roster_positions") or []
    il_slots = sum(1 for s in positions if s in ("IL", "IL+"))
    sched = Schedule(db, days[0] - timedelta(days=1), days[-1])
    lv = LineupValue(active_slots(positions), sched, days, proj, now, today)
    out = {}
    for team, ids in rosters.items():
        ids = {p for p in ids if p in proj}
        if team in il:
            active = ids - il[team]
        else:
            hurt = sorted((p for p in ids if proj[p].status in LONG_OUT), key=lambda p: proj[p].fpts)
            active = ids - set(hurt[:il_slots])
        mean, var = lv.total_stats([active for _ in days])
        wm = mean / weeks_left
        out[team] = TeamWeekly(wm, float(np.sqrt(var / weeks_left + (WEEK_NOISE * wm) ** 2)))
    return out


def playoff_odds(db: Session, league: League, team_id: int, now_utc: datetime | None = None, seed: int = 11) -> dict:
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    today = today_et(now)
    names = team_names(db, league)
    standings = {t.team_id: t for t in db.scalars(select(FantasyTeam).where(FantasyTeam.league_id == league.id))}
    teams = sorted(t for t in standings if standings[t].wins is not None)
    if len(teams) < 2:
        return {"teams": [], "notes": ["Import the League home page (standings) first."]}
    idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)
    spots = min(playoff_spots(league), n_teams)
    week, wstart, wend = current_week(db, league, team_id, today)
    po = playoff_weeks(league, today)
    if week is None or not po:
        return {"teams": [], "notes": ["Needs the current Matchup page and the league Settings page (playoff weeks)."]}
    first_po_week, po_start = po[0][0], po[0][1]
    future_weeks = list(range(week + 1, first_po_week))
    notes = []

    rng = np.random.default_rng(seed)
    wins = np.array([standings[t].wins or 0 for t in teams], dtype=float)[None, :].repeat(SEASONS, 0)
    wins += 0.5 * np.array([standings[t].ties or 0 for t in teams], dtype=float)[None, :]
    points = np.array([standings[t].points_for or 0.0 for t in teams])[None, :].repeat(SEASONS, 0)

    # ---- this week: simulate every matchup from its current score
    this_week = db.scalars(select(Matchup).where(Matchup.league_id == league.id, Matchup.week == week)).all()
    done: set[int] = set()
    my_week_win = None
    for mu in this_week:
        if mu.team_id in done or mu.team_id not in idx or mu.opp_team_id not in idx:
            continue
        o = matchup_outlook(db, league, mu.team_id, now_utc=now, seed=seed + mu.team_id)
        if o is None:
            continue
        a, b = o.sims["me"][:SEASONS], o.sims["opp"][:SEASONS]
        ia, ib = idx[mu.team_id], idx[mu.opp_team_id]
        a_win = a > b
        wins[:, ia] += a_win
        wins[:, ib] += ~a_win
        points[:, ia] += a
        points[:, ib] += b
        done |= {mu.team_id, mu.opp_team_id}
        if team_id in (mu.team_id, mu.opp_team_id):
            my_week_win = a_win if mu.team_id == team_id else ~a_win
    missing = [names.get(t) for t in teams if t not in done]
    if missing:
        notes.append("This week's matchups weren't all found (save the League home page); counted as a coin flip for: "
                     + ", ".join(str(m) for m in missing) + ".")
        rest = [idx[t] for t in teams if t not in done]
        for k in range(0, len(rest) - 1, 2):
            coin = rng.random(SEASONS) < 0.5
            wins[:, rest[k]] += coin
            wins[:, rest[k + 1]] += ~coin

    # ---- later weeks
    if future_weeks:
        days = date_range(wend + timedelta(days=1), po_start - timedelta(days=1))
        rosters, il = team_rosters(db, league)
        strength = _weekly_strength(db, league, {t: rosters.get(t, set()) for t in teams}, il, days, len(future_weeks), now)
        means = np.array([strength[t].mean for t in teams])
        sds = np.array([strength[t].sd for t in teams])
        form = 1 + FORM_SPREAD * rng.standard_normal((SEASONS, n_teams))
        known = {(m.week, m.team_id): m.opp_team_id for m in db.scalars(
            select(Matchup).where(Matchup.league_id == league.id, Matchup.week.in_(future_weeks)))}
        random_weeks = 0
        for w in future_weeks:
            scores = np.maximum(means * form + sds * rng.standard_normal((SEASONS, n_teams)), 0)
            opp = np.empty((SEASONS, n_teams), dtype=int)
            if all((w, t) in known and known[(w, t)] in idx for t in teams):
                opp[:] = [idx[known[(w, t)]] for t in teams]
            else:
                random_weeks += 1
                perm = np.argsort(rng.random((SEASONS, n_teams)), axis=1)  # random pairing: 1st vs 2nd, 3rd vs 4th, ...
                a, b = perm[:, 0::2], perm[:, 1::2]
                rows = np.arange(SEASONS)[:, None]
                opp[rows, a] = b
                opp[rows, b] = a
            opp_scores = np.take_along_axis(scores, opp, axis=1)
            wins += scores > opp_scores
            points += scores
        if random_weeks:
            notes.append(f"Opponents for {random_weeks} of the {len(future_weeks)} remaining weeks are random: the league "
                         "schedule isn't on a saved page yet.")

    # ---- standings: wins, then points for
    key = wins * 1e7 + points
    order = np.argsort(-key, axis=1)
    rank = np.empty_like(order)
    rank[np.arange(SEASONS)[:, None], order] = np.arange(1, n_teams + 1)[None, :]
    made = rank <= spots

    out_teams = []
    for t in teams:
        i = idx[t]
        out_teams.append({
            "team_id": t, "name": names.get(t), "is_me": t == team_id,
            "record": f"{standings[t].wins}-{standings[t].losses}-{standings[t].ties}",
            "playoff_odds": round(float(made[:, i].mean()), 3),
            "avg_seed": round(float(rank[:, i].mean()), 1),
            "proj_wins": round(float(wins[:, i].mean()), 1),
            "seed_chances": [round(float((rank[:, i] == s).mean()), 3) for s in range(1, n_teams + 1)],
        })
    out_teams.sort(key=lambda x: (-x["playoff_odds"], x["avg_seed"]))
    what_if = None
    if my_week_win is not None:
        i = idx[team_id]
        w, lose = my_week_win, ~my_week_win
        what_if = {
            "win_this_week": round(float(made[w, i].mean()), 3) if w.any() else None,
            "lose_this_week": round(float(made[lose, i].mean()), 3) if lose.any() else None,
            "chance_to_win_this_week": round(float(w.mean()), 3),
        }
    return {
        "week": week, "weeks_left": len(future_weeks), "playoff_spots": spots, "first_playoff_week": first_po_week,
        "seasons": SEASONS, "teams": out_teams, "what_if": what_if, "notes": notes,
    }
