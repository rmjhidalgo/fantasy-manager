"""Links to Yahoo pages, so you can make a move there ("Open on Yahoo")."""

from urllib.parse import quote

BASE = "https://basketball.fantasysports.yahoo.com/nba"


def team_url(league_id: int, team_id: int, day: str | None = None) -> str:
    return f"{BASE}/{league_id}/{team_id}/team?date={day}" if day else f"{BASE}/{league_id}/{team_id}"


def add_url(league_id: int, yahoo_id: int) -> str:
    return f"{BASE}/{league_id}/addplayer?apid={yahoo_id}"


def search_url(league_id: int, name: str) -> str:
    return f"{BASE}/{league_id}/players?status=ALL&pos=P&search={quote(name)}"


def player_url(league_id: int, yahoo_id: int | None, name: str) -> str:
    """Add page when the Yahoo id is known, else a player search."""
    return add_url(league_id, yahoo_id) if yahoo_id else search_url(league_id, name)


def league_url(league_id: int, page: str = "") -> str:
    return f"{BASE}/{league_id}/{page}" if page else f"{BASE}/{league_id}"


def players_list_urls(league_id: int, status: str, season: int, pages: int) -> list[str]:
    """The Players list (status A = available, T = taken), season averages, best first, 25 per page."""
    q = f"status={status}&eteam=ALL&fteam=NONE&pos=P&cut_type=33&stat1=S_AS_{season}&myteam=0&sort=PTS&sdir=1"
    return [f"{BASE}/{league_id}/players?{q}" + (f"&count={25 * i}" if i else "") for i in range(pages)]


def matchup_url(league_id: int, week: int | None = None) -> str:
    return f"{BASE}/{league_id}/matchup?week={week}" if week else f"{BASE}/{league_id}/matchup"
