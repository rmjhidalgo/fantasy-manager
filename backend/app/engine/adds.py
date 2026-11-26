"""Adds used this week: from your own entry, or counted from imported transactions.

Yahoo's League page lists recent transactions with times shown in your Yahoo time zone
(the one in the settings page, e.g. "Draft Time: Sun Oct 11 10:00pm JST"). Only the latest
few appear there, so the count is a minimum; your own entry always wins.
"""

import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppSetting, FantasyTeam, League, Transaction
from app.engine.schedule import ET

ZONES = {
    "JST": "Asia/Tokyo", "KST": "Asia/Seoul", "EST": "America/New_York", "EDT": "America/New_York", "ET": "America/New_York",
    "CST": "America/Chicago", "CDT": "America/Chicago", "MST": "America/Denver", "MDT": "America/Denver",
    "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles", "GMT": "UTC", "UTC": "UTC", "BST": "Europe/London",
    "CET": "Europe/Paris", "AEST": "Australia/Sydney", "AEDT": "Australia/Sydney", "SGT": "Asia/Singapore", "PHT": "Asia/Manila",
}
_WHEN = re.compile(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{1,2}):(\d{2}) ([ap]m)")
_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _key(league_id: int, week: int) -> str:
    return f"adds_used:{league_id}:{week}"


def yahoo_zone(league: League) -> ZoneInfo:
    raw = (json.loads(league.settings_json) if league.settings_json else {}).get("raw", {})
    m = re.search(r"\b([A-Z]{2,4})$", (raw.get("Draft Time") or "").strip())
    return ZoneInfo(ZONES.get(m.group(1), "America/New_York") if m else "America/New_York")


def transaction_time(when_text: str | None, zone: ZoneInfo, near: date) -> datetime | None:
    """Time of a transaction like "Nov 26, 7:41 am" (no year: take the one nearest to `near`), timezone-aware."""
    m = _WHEN.search(when_text or "")
    if not m:
        return None
    mon, day, hh, mm, ampm = m.groups()
    hour = int(hh) % 12 + (12 if ampm == "pm" else 0)
    month = _MONTHS.get(mon)
    if not month:
        return None
    year = near.year + (1 if month - near.month < -6 else -1 if month - near.month > 6 else 0)
    return datetime(year, month, int(day), hour, int(mm), tzinfo=zone)


def transaction_date_et(when_text: str | None, zone: ZoneInfo, near: date) -> date | None:
    t = transaction_time(when_text, zone, near)
    return t.astimezone(ET).date() if t else None


# "Buddy Hield CHI - SG,SF Free Agent Jaylen Wells MEM - SG,SF To Waivers" (an injury tag may follow the positions)
_MOVE = re.compile(r"\s*(?P<name>.+?) (?P<team>[A-Z]{2,4}) - (?P<pos>[A-Z,]+)(?: (?P<tag>[A-Z]{1,4}))? (?P<how>To Waivers|Free Agent|Waivers)")


def parse_moves(description: str) -> list[tuple[str, str]]:
    """[(player name, "add" | "drop")] from a transaction description."""
    return [(m.group("name").strip(), "drop" if m.group("how") == "To Waivers" else "add") for m in _MOVE.finditer(description)]


def waiver_days(league: League) -> int:
    raw = (json.loads(league.settings_json) if league.settings_json else {}).get("raw", {})
    m = re.search(r"(\d+)", raw.get("Waiver Time") or "")
    return int(m.group(1)) if m else 2


def counted_adds(db: Session, league: League, team_id: int, start: date, end: date) -> list[dict]:
    team = db.get(FantasyTeam, (league.id, team_id))
    if team is None or not team.name:
        return []
    zone = yahoo_zone(league)
    out = []
    for t in db.scalars(select(Transaction).where(Transaction.league_id == league.id, Transaction.team_name == team.name)):
        # An add shows the player then where he came from: "Free Agent" or "Waivers" (drops say "To Waivers").
        adds = sum(1 for _, action in parse_moves(t.description) if action == "add")
        if not adds:
            continue
        d = transaction_date_et(t.when_text, zone, start)
        if d and start <= d <= end:
            out.append({"when": t.when_text, "description": t.description, "adds": adds})
    return out


def adds_used(db: Session, league: League, team_id: int, week: int | None, start: date, end: date) -> dict:
    counted = counted_adds(db, league, team_id, start, end)
    n_counted = sum(c["adds"] for c in counted)
    row = db.get(AppSetting, _key(league.id, week)) if week is not None else None
    manual = int(row.value) if row and row.value not in (None, "") else None
    settings = json.loads(league.settings_json) if league.settings_json else {}
    limit = settings.get("max_adds_per_week")
    used = manual if manual is not None else n_counted
    return {
        "week": week,
        "limit": limit,
        "used": used,
        "left": max(0, limit - used) if limit is not None else None,
        "manual": manual,
        "counted": n_counted,
        "counted_from": counted,
        "source": "you" if manual is not None else "transactions",
    }


def set_adds_used(db: Session, league: League, week: int, used: int | None) -> None:
    key = _key(league.id, week)
    row = db.get(AppSetting, key)
    value = None if used is None else str(used)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()
