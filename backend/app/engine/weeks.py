"""Matchup week dates for the Suggested Moves horizons.

Yahoo weeks run Monday-Sunday, but some are longer (e.g. the All-Star break week), so
counting 7-day weeks from the current one drifts over a season. So:
- next week / next 5 weeks: counted forward from the current week (close enough nearby);
- playoffs: counted back from the playoff end date on the settings page
  ("8 teams - Week 20, 21 and 22 (ends Sunday, Apr 4)"); playoff weeks are regular weeks.
"""

import json
import re
from datetime import date, timedelta

from app.db.models import League

_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def playoff_end(league: League, near: date) -> date | None:
    raw = (json.loads(league.settings_json) if league.settings_json else {}).get("raw", {})
    m = re.search(r"ends \w+, ([A-Z][a-z]{2}) (\d{1,2})", raw.get("Playoffs") or "")
    if not m or m.group(1) not in _MONTHS:
        return None
    month, day = _MONTHS[m.group(1)], int(m.group(2))
    # the playoffs end in spring of the season that `near` belongs to
    year = near.year + 1 if near.month >= 7 else near.year
    return date(year, month, day)


def playoff_weeks(league: League, near: date) -> list[tuple[int, date, date]]:
    """[(week, start, end)] for the playoff weeks, or [] if unknown."""
    settings = json.loads(league.settings_json) if league.settings_json else {}
    weeks = sorted(settings.get("playoff_weeks") or [])
    end = playoff_end(league, near)
    if not weeks or end is None:
        return []
    out = []
    for k, w in enumerate(reversed(weeks)):
        e = end - timedelta(days=7 * k)
        out.append((w, e - timedelta(days=6), e))
    return sorted(out)


def weeks_after(current_week: int | None, current_end: date, n: int) -> list[tuple[int | None, date, date]]:
    """The n weeks after the current one, assuming Monday-Sunday weeks."""
    out = []
    for k in range(n):
        s = current_end + timedelta(days=1 + 7 * k)
        out.append((current_week + 1 + k if current_week else None, s, s + timedelta(days=6)))
    return out
