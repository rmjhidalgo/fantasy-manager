"""Daily summary: one short read each morning.

Import reminder, lineup fixes for today, injuries, the best pickups for your chosen
horizon, this week's matchup and your playoff chances. Shown on the Overview tab; the app
also sends a desktop notification at your chosen time (while it's open in a browser tab).
"""

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AppSetting, League
from app.engine.alerts import build_alerts
from app.engine.playoffs import playoff_odds
from app.engine.simulator import matchup_outlook
from app.engine.suggest import HORIZON_NAMES, suggest_moves

DEFAULTS = {"enabled": True, "time": "07:00", "horizon": "A"}


def get_settings(db: Session) -> dict:
    row = db.get(AppSetting, "summary_settings")
    try:
        return {**DEFAULTS, **(json.loads(row.value) if row and row.value else {})}
    except ValueError:
        return dict(DEFAULTS)


def set_settings(db: Session, enabled: bool, time: str, horizon: str) -> dict:
    row = db.get(AppSetting, "summary_settings") or AppSetting(key="summary_settings")
    row.value = json.dumps({"enabled": enabled, "time": time, "horizon": horizon})
    db.add(row)
    db.commit()
    return get_settings(db)


def build_summary(db: Session, league: League, team_id: int, lineup_today: dict | None = None,
                  now_utc: datetime | None = None) -> dict:
    now = now_utc or datetime.now(UTC).replace(tzinfo=None)
    settings = get_settings(db)
    items: list[dict] = []

    def add(kind: str, title: str, detail: str = "", action: str | None = None, level: str = "info") -> None:
        items.append({"kind": kind, "title": title, "detail": detail, "action": action, "level": level})

    alerts = build_alerts(db, league, now_utc=now)
    stale = [a for a in alerts if a["key"].startswith(("stale:", "missing:"))]
    if stale:
        add("import", "Save fresh pages", "; ".join(a["title"] for a in stale) + ".", "import", "warn")

    if lineup_today:
        changes = [p for p in lineup_today["players"] if p["change"] in ("start", "bench")]
        gain = lineup_today["best_expected"] - lineup_today["current_expected"]
        if changes and gain > 0.5:
            add("lineup", f"Lineup today: +{gain:.1f} pts",
                ", ".join(f"{'start' if c['change'] == 'start' else 'bench'} {c['name']}" for c in changes) + ".", "lineup", "warn")
        else:
            add("lineup", "Lineup today is set", "Your saved lineup is already the best one.", "lineup")
        for m in lineup_today.get("il_moves", []):
            add("lineup", f"{'Move ' + m['name'] + ' to IL' if m['move'] == 'to IL' else 'Activate ' + m['name']}", m["reason"], "lineup", "warn")

    for a in alerts:
        if a["key"].startswith(("out:", "doubt:", "absent:", "il-healthy:")):
            add("injury", a["title"], a["detail"], "lineup", a["level"])

    horizon = settings["horizon"]
    try:
        s = suggest_moves(db, league, team_id, horizon, now_utc=now)
        if s["moves"]:
            top = s["moves"][:2]
            add("moves", f"Best moves ({HORIZON_NAMES[horizon].lower()}): +{sum(m['gain'] for m in top):.0f} pts",
                "; ".join(f"add {m['add']['name']}" + (f" for {m['drop']['name']}" if m["drop"] else "") + f" (+{m['gain']:.0f})"
                          for m in top) + ".", "suggest")
        else:
            add("moves", f"Moves ({HORIZON_NAMES[horizon].lower()}): hold", "No add is worth it right now.", "suggest")
    except ValueError:
        pass

    o = matchup_outlook(db, league, team_id, now_utc=now)
    if o:
        add("matchup", f"Week {o.week}: {o.me.current:.0f}–{o.opp.current:.0f}, {round(o.win_prob * 100)}% to win",
            f"Projected {o.me.final_expected:.0f}–{o.opp.final_expected:.0f}, {o.me.games_left} vs {o.opp.games_left} games left.",
            "matchup", "info" if o.win_prob >= 0.5 else "warn")

    odds = playoff_odds(db, league, team_id, now_utc=now)
    me = next((t for t in odds.get("teams", []) if t["is_me"]), None)
    if me:
        wi = odds.get("what_if") or {}
        detail = f"Projected seed {me['avg_seed']:.0f}, about {me['proj_wins']:.0f} wins."
        if wi.get("win_this_week") is not None and wi.get("lose_this_week") is not None:
            detail += f" Win this week: {wi['win_this_week']:.0%}; lose: {wi['lose_this_week']:.0%}."
        add("playoffs", f"Playoff chance: {me['playoff_odds']:.0%}", detail, "strategy")

    return {"generated_at": now.isoformat() + "Z", "settings": settings, "items": items}
