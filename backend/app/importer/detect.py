"""Work out which kind of Yahoo Fantasy Basketball page a URL is."""

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

_PATH = re.compile(r"^/nba/(\d+)(?:/([^/?#]+))?/?$")

# URL path segment after the league ID -> page type
_NAMED = {
    "settings": "settings",
    "matchup": "matchup",
    "players": "players",
    "standings": "standings",
    "transactions": "transactions",
}


@dataclass
class PageKind:
    page_type: str  # settings | league_home | standings | team | matchup | players | transactions
    league_id: int
    team_id: int | None = None
    params: dict[str, str] = field(default_factory=dict)


def detect(url: str | None) -> PageKind | None:
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.netloc.endswith("basketball.fantasysports.yahoo.com"):
        return None
    m = _PATH.match(parts.path)
    if not m:
        return None
    league_id = int(m.group(1))
    seg = m.group(2)
    params = {k.lower(): v[0] for k, v in parse_qs(parts.query).items() if v}
    if seg is None:
        return PageKind("league_home", league_id, params=params)
    if seg.isdigit():
        return PageKind("team", league_id, team_id=int(seg), params=params)
    if seg in _NAMED:
        return PageKind(_NAMED[seg], league_id, params=params)
    return None


PAGE_LABELS = {
    "settings": "League settings",
    "league_home": "League home (standings)",
    "standings": "Standings",
    "team": "Team roster",
    "matchup": "Matchup",
    "players": "Players list",
    "transactions": "Transactions",
}
