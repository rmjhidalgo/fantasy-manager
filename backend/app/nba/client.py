"""Download NBA data: the season schedule (cdn.nba.com) and player game logs (stats.nba.com).

NBA's servers refuse requests that don't look like a browser, so we send normal
browser headers. Everything is fetched from this PC's own internet connection.
"""

import time

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}
STATS_HEADERS = {**HEADERS, "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}

SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
# Injured players with estimated return dates (ESPN's public injury list; the official NBA report is PDF only)
INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
STATS_URL = "https://stats.nba.com/stats"


class NbaDataError(RuntimeError):
    pass


def _get(url: str, headers: dict, params: dict | None = None, tries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            r = httpx.get(url, headers=headers, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            last = NbaDataError(f"{url} answered HTTP {r.status_code}")
        except (httpx.HTTPError, ValueError) as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise NbaDataError(f"Couldn't download NBA data from {url}: {last}")


def fetch_schedule() -> dict:
    return _get(SCHEDULE_URL, HEADERS)["leagueSchedule"]


def season_string(schedule_season_year: str) -> str:
    """'2026-27' stays as is; NBA stats endpoints use the same form."""
    return schedule_season_year


def _rows(data: dict) -> list[dict]:
    rs = data["resultSets"][0]
    return [dict(zip(rs["headers"], row, strict=False)) for row in rs["rowSet"]]


def fetch_game_logs(season: str) -> list[dict]:
    """Every player's box score line for every game this regular season (one request)."""
    return _rows(
        _get(
            f"{STATS_URL}/leaguegamelog",
            STATS_HEADERS,
            {
                "Counter": 0,
                "Direction": "DESC",
                "LeagueID": "00",
                "PlayerOrTeam": "P",
                "Season": season,
                "SeasonType": "Regular Season",
                "Sorter": "DATE",
            },
        )
    )


def fetch_injuries() -> list[dict]:
    """[{name, team, status, return_date, injury, comment, reported}] for every injured player."""
    data = _get(INJURIES_URL, {"User-Agent": HEADERS["User-Agent"], "Accept": "application/json"})
    out = []
    for team in data.get("injuries", []):
        for i in team.get("injuries", []):
            a = i.get("athlete") or {}
            d = i.get("details") or {}
            injury = " - ".join(x for x in (d.get("type"), d.get("detail")) if x) or None
            out.append({
                "name": a.get("displayName") or "",
                "team": (a.get("team") or {}).get("abbreviation"),
                "status": i.get("status") or "Out",
                "return_date": (d.get("returnDate") or "")[:10] or None,
                "injury": injury,
                "comment": i.get("shortComment"),
                "reported": (i.get("date") or "")[:10] or None,
            })
    return out


def fetch_player_index(season: str) -> list[dict]:
    """Current players with their NBA.com position (G, F, C, G-F, F-C, ...)."""
    params = {
        "LeagueID": "00", "Season": season, "Historical": 0, "TeamID": 0, "Active": "", "AllStar": "", "College": "",
        "Country": "", "DraftPick": "", "DraftRound": "", "DraftYear": "", "Height": "", "Weight": "", "PlayerPosition": "",
    }
    return _rows(_get(f"{STATS_URL}/playerindex", STATS_HEADERS, params))


def fetch_players(season: str) -> list[dict]:
    """All players on NBA rosters this season (including ones who haven't played yet)."""
    return _rows(
        _get(
            f"{STATS_URL}/commonallplayers",
            STATS_HEADERS,
            {"IsOnlyCurrentSeason": 1, "LeagueID": "00", "Season": season},
        )
    )
