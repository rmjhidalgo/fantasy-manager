"""Strategy views: schedule grid, player comparison, opponent scouting, scoring profile."""

import json
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FantasyTeam, GameLog, League, Matchup, NbaGame, NbaPlayer, Ownership, Player, PlayerMap, PlayerStats
from app.engine.adds import counted_adds
from app.engine.freeagents import current_week
from app.engine.lineup import active_slots
from app.engine.movelog import my_transactions
from app.engine.projections import Projection, project_nba_players, project_players, virtual_id
from app.engine.rosters import scheduled_opponent, team_names, team_rosters
from app.engine.schedule import Schedule, date_range, today_et
from app.engine.scoring import YAHOO_TO_LOG, fantasy_points, league_weights
from app.engine.suggest import LONG_OUT
from app.engine.weeks import playoff_weeks
from app.nba.matching import norm_name

# ---------------------------------------------------------------- schedule grid


def schedule_grid(db: Session, league: League, team_id: int, now_utc: datetime | None = None) -> dict:
    """NBA teams x matchup weeks: games left this week, then each Monday-Sunday week to the end of the playoffs."""
    today = today_et(now_utc)
    week, _, wend = current_week(db, league, team_id, today)
    playoffs = playoff_weeks(league, today)
    playoff_by_start = {s: w for w, s, _ in playoffs}
    last = playoffs[-1][2] if playoffs else None
    if last is None:
        last_game = db.scalar(select(NbaGame.date_et).where(NbaGame.regular_season == 1).order_by(NbaGame.date_et.desc()).limit(1))
        last = date.fromisoformat(last_game) if last_game else wend
    cols = [{"label": f"Week {week}" if week else "This week", "start": today, "end": wend, "playoff": False, "current": True}]
    s = wend + timedelta(days=1)
    while s <= last:
        e = s + timedelta(days=6)
        pw = playoff_by_start.get(s)
        cols.append({"label": f"Week {pw}" if pw else f"{s:%b} {s.day}", "start": s, "end": e, "playoff": pw is not None, "current": False})
        s = e + timedelta(days=1)

    sched = Schedule(db, today - timedelta(days=1), last)
    teams = sorted({t for g in sched.games for t in (g.home, g.away)})
    rows = []
    for t in teams:
        counts, b2b = [], []
        for c in cols:
            ds = [d for d in date_range(c["start"], c["end"]) if sched.game(t, d)]
            counts.append(len(ds))
            b2b.append(sum(1 for d in ds if sched.is_back_to_back(t, d)))
        rows.append({"team": t, "games": counts, "back_to_backs": b2b,
                     "playoff_games": sum(n for n, c in zip(counts, cols, strict=True) if c["playoff"])})

    # Your players by NBA team, and your roster's total games per week
    rosters, il = team_rosters(db, league)
    mine = rosters.get(team_id, set()) - il.get(team_id, set())
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(mine)))}
    mine_by_team: dict[str, list[str]] = defaultdict(list)
    for p in players.values():
        if p.nba_team:
            mine_by_team[p.nba_team].append(p.name)
    by_team = {r["team"]: r for r in rows}
    my_games = [sum(len(v) * by_team[t]["games"][i] for t, v in mine_by_team.items() if t in by_team) for i in range(len(cols))]
    for r in rows:
        r["my_players"] = sorted(mine_by_team.get(r["team"], []))
    return {
        "columns": [{**c, "start": c["start"].isoformat(), "end": c["end"].isoformat()} for c in cols],
        "teams": rows,
        "my_games": my_games,
        "notes": ["Weeks after the current one are Monday–Sunday; Yahoo may merge a couple of them (e.g. the All-Star break)."]
        if playoffs else ["Playoff weeks unknown: import the league Settings page."],
    }


# ---------------------------------------------------------------- player search + comparison


def _owners(db: Session, league: League) -> dict[int, str]:
    names = team_names(db, league)
    out = {}
    for o in db.scalars(select(Ownership).where(Ownership.league_id == league.id)):
        out[o.player_id] = names.get(o.team_id, "a team") if o.kind == "team" else ("Free agent" if o.kind == "FA" else "Waivers")
    return out


def player_search(db: Session, league: League, q: str, limit: int = 15) -> list[dict]:
    """Players whose name contains q: Yahoo players from saved pages, plus NBA players not on any saved page."""
    key = norm_name(q)
    if len(key) < 2:
        return []
    owners = _owners(db, league)
    mapped = {m.nba_id for m in db.scalars(select(PlayerMap)) if m.nba_id}
    out = []
    for p in db.scalars(select(Player)):
        if key in norm_name(p.name):
            out.append({"id": p.id, "name": p.name, "nba_team": p.nba_team, "positions": (p.positions or "").split(","),
                        "owner": owners.get(p.id, "Unknown")})
    for p in db.scalars(select(NbaPlayer)):
        if p.id not in mapped and key in norm_name(p.name):
            out.append({"id": virtual_id(p.id), "name": p.name, "nba_team": p.team, "positions": [], "owner": "Not on a saved page"})
    out.sort(key=lambda r: (not norm_name(r["name"]).startswith(key), r["name"]))
    return out[:limit]


def _project_any(db: Session, league: League, ids: list[int], today: date) -> dict[int, Projection]:
    proj = project_players(db, league, [i for i in ids if i > 0], today)
    proj.update(project_nba_players(db, league, [-i for i in ids if i < 0], today))
    return proj


def compare_players(db: Session, league: League, team_id: int, ids: list[int], now_utc: datetime | None = None) -> dict:
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    today = today_et(now)
    ids = ids[:4]
    proj = _project_any(db, league, ids, today)
    weights, _ = league_weights(league)
    owners = _owners(db, league)
    nba_of = {m.yahoo_id: m.nba_id for m in db.scalars(select(PlayerMap).where(PlayerMap.yahoo_id.in_([i for i in ids if i > 0])))}
    week, _, wend = current_week(db, league, team_id, today)
    playoffs = playoff_weeks(league, today)
    windows = {"rest_of_week": (today, wend), "next_7": (today, today + timedelta(days=6)), "next_14": (today, today + timedelta(days=13))}
    if playoffs:
        windows["playoffs"] = (playoffs[0][1], playoffs[-1][2])
    sched = Schedule(db, today, max(e for _, e in windows.values()))
    yahoo_stats = {s.player_id: s for s in db.scalars(select(PlayerStats).where(PlayerStats.league_id == league.id))
                   if s.window.startswith("S_AS")}

    out = []
    for pid in ids:
        p = proj.get(pid)
        if p is None:
            continue
        nba = nba_of.get(pid) if pid > 0 else -pid
        logs = sorted(db.scalars(select(GameLog).where(GameLog.player_id == nba)), key=lambda g: g.date_et) if nba else []
        fp = [round(fantasy_points(g, weights), 1) for g in logs]
        q = statistics.quantiles(fp, n=4) if len(fp) >= 4 else None
        games = {k: sum(1 for d in date_range(s, e) if sched.game(p.nba_team, d) and d >= today) for k, (s, e) in windows.items()}
        ys = yahoo_stats.get(pid)
        out.append({
            "id": pid, "name": p.name, "nba_team": p.nba_team, "positions": p.positions, "positions_estimated": p.positions_estimated,
            "status": p.status, "owner": owners.get(pid, "Not on a saved page" if pid < 0 else "Unknown"),
            "fpts": p.fpts, "play_prob": p.play_prob, "window_fp": p.window_fp, "recent_mpg": p.recent_mpg, "season_mpg": p.season_mpg,
            "games_played": len(fp), "sd": round(statistics.pstdev(fp), 1) if len(fp) >= 2 else None,
            "floor": round(q[0], 1) if q else None, "ceiling": round(q[2], 1) if q else None,
            "missed_streak": p.missed_streak,
            "last_games": [{"date": g.date_et, "fp": v, "min": g.min} for g, v in list(zip(logs, fp, strict=True))[-10:]],
            "games": games, "pct_rostered": ys.pct_rostered if ys else None,
        })
    return {"players": out, "windows": {k: [s.isoformat(), e.isoformat()] for k, (s, e) in windows.items()}}


# ---------------------------------------------------------------- opponent scouting


def scout_opponent(db: Session, league: League, team_id: int, now_utc: datetime | None = None) -> dict:
    """The current matchup opponent (and next week's, if its Matchup page was saved): roster, injuries, adds, transactions."""
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    today = today_et(now)
    week, start, end = current_week(db, league, team_id, today)
    names = team_names(db, league)
    out = {"week": week, "opponents": []}
    rosters, il = team_rosters(db, league)
    for w in ([week, week + 1] if week else []):
        mu = db.scalar(select(Matchup).where(Matchup.league_id == league.id, Matchup.team_id == team_id, Matchup.week == w))
        opp = mu.opp_team_id if mu else scheduled_opponent(db, league, team_id, w)
        if opp is None:
            continue
        ids = list(rosters.get(opp, set()))
        proj = project_players(db, league, ids, today)
        t = db.get(FantasyTeam, (league.id, opp))
        if mu and mu.start_date:
            wstart, wend = date.fromisoformat(mu.start_date), date.fromisoformat(mu.end_date)
        elif w == week:
            wstart, wend = start, end
        else:  # next week: Monday-Sunday after this one
            wstart, wend = end + timedelta(days=1), end + timedelta(days=7)
        sched = Schedule(db, max(today, wstart), wend)
        roster = []
        for pid in ids:
            p = proj.get(pid)
            if not p:
                continue
            games = sum(1 for d in date_range(max(today, wstart), wend) if sched.game(p.nba_team, d))
            roster.append({"name": p.name, "nba_team": p.nba_team, "positions": p.positions, "status": p.status, "fpts": p.fpts,
                           "games_left": games, "on_il": pid in il.get(opp, set()), "missed_streak": p.missed_streak})
        roster.sort(key=lambda r: -r["fpts"])
        team_tx = my_transactions(db, league, opp)  # works for any team
        out["opponents"].append({
            "week": w, "team": {"id": opp, "name": names.get(opp), "rank": t.rank if t else None,
                                "record": f"{t.wins}-{t.losses}-{t.ties}" if t and t.wins is not None else None,
                                "points_for": t.points_for if t else None},
            "score": {"me": mu.score, "them": mu.opp_score, "as_of": mu.as_of.isoformat() + "Z" if mu.as_of else None}
            if mu else None,
            "roster": roster,
            "injured": [r for r in roster if r["status"] in LONG_OUT | {"D", "Q", "GTD"} or r["missed_streak"] >= 3],
            "games_left": sum(r["games_left"] for r in roster if not r["on_il"] and r["status"] not in LONG_OUT),
            "adds_this_week": sum(c["adds"] for c in counted_adds(db, league, opp, start, end)) if w == week else None,
            "transactions": team_tx,
        })
    return out


# ---------------------------------------------------------------- scoring profile


def scoring_profile(db: Session, league: League, team_id: int, now_utc: datetime | None = None) -> dict:
    """Where each team's fantasy points come from (per game, season averages of its current players)."""
    today = today_et(now_utc)
    weights, _ = league_weights(league)  # keyed by box-score column
    label = {}
    for abbr, col in YAHOO_TO_LOG.items():
        label.setdefault(col, abbr)
    cats = [(label.get(col, col.upper()), col) for col in weights]
    weights = {label.get(col, col.upper()): w for col, w in weights.items()}
    rosters, il = team_rosters(db, league)
    names = team_names(db, league)
    all_ids = {p for ids in rosters.values() for p in ids}
    status = {p.id: p.status for p in db.scalars(select(Player).where(Player.id.in_(all_ids)))}
    nba_of = {m.yahoo_id: m.nba_id for m in db.scalars(select(PlayerMap).where(PlayerMap.yahoo_id.in_(all_ids))) if m.nba_id}
    per_game: dict[int, dict[str, float]] = {}
    logs_by: dict[int, list[GameLog]] = defaultdict(list)
    for g in db.scalars(select(GameLog).where(GameLog.player_id.in_(list(nba_of.values())), GameLog.date_et < today.isoformat())):
        logs_by[g.player_id].append(g)
    for yid, nid in nba_of.items():
        logs = logs_by.get(nid)
        if logs:
            per_game[yid] = {cat: statistics.fmean(getattr(g, col) or 0 for g in logs) * weights[cat] for cat, col in cats}

    settings = json.loads(league.settings_json) if league.settings_json else {}
    n_starters = len(active_slots(settings.get("roster_positions")))
    teams = []
    for tid, ids in rosters.items():
        # A team's points come from its starters: its best healthy players, one per lineup slot.
        # (IL slots of teams whose roster page wasn't saved are unknown, so injured players are left out everywhere.)
        healthy = [p for p in ids if p in per_game and p not in il.get(tid, set()) and status.get(p) not in LONG_OUT]
        best = sorted(healthy, key=lambda p: -sum(per_game[p].values()))[:n_starters]
        fp = {cat: sum(per_game[p][cat] for p in best) for cat, _ in cats}
        total = sum(fp.values())
        teams.append({"team_id": tid, "name": names.get(tid), "is_me": tid == team_id, "total": round(total, 1),
                      "by_category": {c: round(v, 1) for c, v in fp.items()},
                      "share": {c: round(v / total, 3) if total else 0 for c, v in fp.items()}})
    if not teams:
        return {"teams": [], "categories": [], "league_average": {}, "my_rank": {}}
    avg = {c: round(statistics.fmean(t["by_category"][c] for t in teams), 1) for c, _ in cats}
    ranks = {}
    me = next((t for t in teams if t["is_me"]), None)
    if me:
        for c, _ in cats:
            order = sorted(teams, key=lambda t: -t["by_category"][c])  # more FP is better (fewer turnovers = less negative)
            ranks[c] = 1 + [t["team_id"] for t in order].index(team_id)
    league_total = sum(avg.values())
    teams.sort(key=lambda t: -t["total"])
    return {
        "categories": [{"key": c, "weight": weights[c], "league_share": round(avg[c] / league_total, 3) if league_total else 0}
                       for c, _ in cats],
        "teams": teams,
        "league_average": avg,
        "my_rank": ranks,
        "note": f"Each team's best {n_starters} healthy players (one per lineup slot): season per-game averages times your "
                "league's scoring. Injured players are left out.",
    }
