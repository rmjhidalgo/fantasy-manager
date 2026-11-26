"""Alerts for the active team: injuries, lineup problems today, adds left, and stale data.

Each alert has a stable `key`: the app shows a desktop notification only for keys it
hasn't notified before.
"""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import League, Matchup, PlayerMap, RosterSlot
from app.engine.adds import adds_used
from app.engine.freeagents import current_week
from app.engine.lineup import INACTIVE_SLOTS, Candidate, active_slots, optimize_day
from app.engine.next_man_up import next_man_up
from app.engine.pool import available_pool
from app.engine.projections import ABSENT_GAMES, injury_text, project_players
from app.engine.schedule import Schedule, today_et
from app.nba import sync

LONG_OUT = {"O", "INJ", "OFS", "SUSP", "NA"}
DOUBTFUL = {"D", "Q", "GTD"}
IL_SLOTS = {"IL", "IL+"}
STATUS_TEXT = {"O": "Out", "INJ": "Injured", "OFS": "Out for season", "SUSP": "Suspended", "NA": "Not active",
               "D": "Doubtful", "Q": "Questionable", "GTD": "Game-time decision", "P": "Probable"}

# Data older than this (hours) gets a reminder to re-save the page
STALE_HOURS = {"roster": 24, "matchup": 24, "available": 48, "rostered": 72, "nba": 6}


def _alert(key: str, level: str, title: str, detail: str = "", action: str | None = None, **extra) -> dict:
    return {"key": key, "level": level, "title": title, "detail": detail, "action": action, **extra}


def _hours(now: datetime, t: datetime | None) -> float | None:
    return (now - t).total_seconds() / 3600 if t else None


def build_alerts(db: Session, league: League, now_utc: datetime | None = None) -> list[dict]:
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    today = today_et(now)
    out: list[dict] = []
    team_id = league.my_team_id
    if not team_id:
        return [_alert("no-team", "warn", "Your team isn't known yet", "Import any page from your league while signed in.", "import")]

    settings = json.loads(league.settings_json) if league.settings_json else {}
    positions = settings.get("roster_positions") or []
    roster = db.scalars(select(RosterSlot).where(RosterSlot.league_id == league.id, RosterSlot.team_id == team_id)).all()
    proj = project_players(db, league, [r.player_id for r in roster], today)
    nba_of = {m.yahoo_id: m.nba_id for m in db.scalars(select(PlayerMap).where(PlayerMap.yahoo_id.in_([r.player_id for r in roster])))}
    pool, info = available_pool(db, league)
    pool_nba = {pp.nba_id: pp for pp in pool if pp.nba_id}

    # ---- injuries
    il_total = sum(1 for s in positions if s in IL_SLOTS)
    il_used = sum(1 for r in roster if r.slot in IL_SLOTS)
    for r in roster:
        p = proj.get(r.player_id)
        if not p:
            continue
        in_lineup = r.slot not in INACTIVE_SLOTS
        inj = injury_text(p, today)  # expected return from ESPN's injury list, if he's on it
        out_now = p.status in LONG_OUT or (p.injury is not None and p.available_from() is not None and p.available_from() > today)
        if r.slot in IL_SLOTS and p.status not in LONG_OUT | DOUBTFUL | {"P"} and not out_now:
            out.append(_alert(f"il-healthy:{r.player_id}", "danger", f"{p.name} is in an IL slot but no longer injured",
                              "Yahoo blocks adds and drops until he's moved out of the IL slot.", "lineup", player_id=r.player_id))
            continue
        if out_now and r.slot not in IL_SLOTS:
            label = STATUS_TEXT.get(p.status, p.status) if p.status in LONG_OUT else "Out"
            detail = f"{inj} (ESPN's estimate)." if inj else f"{label}."
            if p.status not in LONG_OUT:
                detail += " Yahoo hasn't tagged him (on your saved pages) yet."
            if il_used < il_total:
                detail += " An IL slot is free: moving him there opens a roster spot for a pickup."
            helpers = []
            nba = nba_of.get(r.player_id)
            if nba and p.nba_team:
                for b in next_man_up(db, league, nba, p.nba_team):
                    pp = pool_nba.get(b.nba_id)
                    helpers.append({
                        "name": b.name, "minutes_with": b.minutes_with, "minutes_without": b.minutes_without,
                        "fpts_without": b.fpts_without, "games_without": b.games_without,
                        "available": pp is not None, "kind": pp.kind if pp else None, "yahoo_id": pp.yahoo_id if pp else None,
                    })
            out.append(_alert(f"out:{r.player_id}:{p.status}:{p.return_date}", "danger" if in_lineup else "warn",
                              f"{p.name} ({p.nba_team}): {label}", detail,
                              "lineup", player_id=r.player_id, next_man_up=helpers, return_date=p.return_date.isoformat() if p.return_date else None))
        elif r.slot in IL_SLOTS and inj:
            out.append(_alert(f"il:{r.player_id}:{p.return_date}", "info", f"{p.name} (on IL): {inj[0].lower() + inj[1:]}",
                              "ESPN's estimate. Move him back to your lineup when he returns.", "lineup", player_id=r.player_id,
                              notify=False))
        elif p.status in DOUBTFUL:
            out.append(_alert(f"doubt:{r.player_id}:{p.status}", "warn", f"{p.name} ({p.nba_team}): {STATUS_TEXT[p.status]}",
                              "Check before his game; the projections count him at reduced odds.", "lineup", player_id=r.player_id))
        elif p.status is None and p.missed_streak >= ABSENT_GAMES and r.slot not in IL_SLOTS:
            out.append(_alert(f"absent:{r.player_id}:{p.missed_streak}", "warn",
                              f"{p.name} has missed {p.nba_team}'s last {p.missed_streak} games",
                              "He has no injury tag on your saved pages, which may be out of date. Re-save your team page.",
                              "import", player_id=r.player_id))

    # ---- lineup today
    sched = Schedule(db, today - timedelta(days=1), today)
    slots = active_slots(positions)
    cands, has_game, starters_no_game = [], [], []
    for r in roster:
        p = proj.get(r.player_id)
        if not p or r.slot in IL_SLOTS:
            continue
        g = sched.game(p.nba_team, today)
        if g:
            if g.status == 1 and not (g.start_utc and g.start_utc <= now):
                has_game.append(r.player_id)  # can still be moved into the lineup
            cands.append(Candidate(r.player_id, p.positions, p.play_prob_on(sched.is_back_to_back(p.nba_team, today), today) * p.fpts))
        elif r.slot not in INACTIVE_SLOTS:
            starters_no_game.append(p.name)
    best = optimize_day(slots, cands)
    empty = len(slots) - len(best.assignments)
    slot_of = {r.player_id: r.slot for r in roster}
    benched = [proj[pid].name for pid in has_game if pid in best.assignments and slot_of[pid] in INACTIVE_SLOTS]
    if benched:
        out.append(_alert(f"bench:{today}:{','.join(sorted(benched))}", "warn",
                          f"Start {', '.join(benched)} today", "They have games but are on your bench (as last saved).", "lineup"))
    nba_games_today = any(g.date_et == today.isoformat() for g in sched.games)
    if empty > 0 and nba_games_today:  # no NBA games at all (e.g. Thanksgiving): nothing to fill
        out.append(_alert(f"empty:{today}:{empty}", "info", f"{empty} empty lineup slot{'s' if empty > 1 else ''} today",
                          f"Only {len(best.assignments)} of your players can fill a slot today. A streamer could use the gap.",
                          "streaming"))

    # ---- adds
    week, start, end = current_week(db, league, team_id, today)
    a = adds_used(db, league, team_id, week, start, end)
    if a["limit"] is not None:
        src = "the number you entered" if a["source"] == "you" else "counted from your saved Transactions/League pages (save Transactions daily for an exact count)"
        out.append(_alert(f"adds:{week}:{a['used']}", "info", f"Adds this week: {a['used']} of {a['limit']} used",
                          f"{a['left']} left. Used = {src}.", "streaming", notify=False))

    # ---- stale data
    def stale(key: str, label: str, t: datetime | None, page: str) -> None:
        h = _hours(now, t)
        if h is None:
            out.append(_alert(f"missing:{key}", "warn", f"No {label} imported yet", f"Save your {page} page.", "import", notify=False))
        elif h > STALE_HOURS[key]:
            out.append(_alert(f"stale:{key}:{t.isoformat()}", "info", f"{label.capitalize()} is {h / 24:.1f} days old" if h >= 48 else
                              f"{label.capitalize()} is {h:.0f} hours old", f"Re-save your {page} page for current data.", "import", notify=False))

    my_times = [r.as_of for r in roster if r.as_of]
    stale("roster", "your roster", max(my_times) if my_times else None, "Team")
    mu = db.scalar(select(Matchup).where(Matchup.league_id == league.id, Matchup.team_id == team_id).order_by(Matchup.week.desc()).limit(1))
    stale("matchup", "the matchup", mu.as_of if mu else None, "Matchup")
    stale("available", "the available players list", info.available_as_of, "Players (Available)")
    stale("rostered", "the taken players list", info.rostered_as_of, "Players (Taken)")
    at = sync.refreshed_at()
    h = _hours(now, at)
    if sync.last_error:
        out.append(_alert("nba-error", "warn", "NBA data couldn't be updated", sync.last_error, "import", notify=False))
    elif h is None or h > STALE_HOURS["nba"]:
        out.append(_alert("nba-stale", "info", "NBA data is out of date", "It updates every 3 hours while the app runs; use Refresh now on the Import & data tab.", "import", notify=False))
    if not settings:
        out.append(_alert("missing:settings", "warn", "League settings not imported", "Save your league's Settings page.", "import", notify=False))

    order = {"danger": 0, "warn": 1, "info": 2}
    out.sort(key=lambda a: order[a["level"]])
    for a in out:
        a.setdefault("notify", a["level"] != "info" or a["key"].startswith("empty:"))
    return out
