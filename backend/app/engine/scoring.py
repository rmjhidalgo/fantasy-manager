"""Fantasy points from a stat line, using the league's own scoring weights."""

import json

from app.db.models import GameLog, League

# Yahoo stat abbreviation -> GameLog column
YAHOO_TO_LOG = {
    "PTS": "pts",
    "REB": "reb",
    "AST": "ast",
    "ST": "stl",
    "STL": "stl",
    "BLK": "blk",
    "TO": "tov",
    "3PTM": "fg3m",
    "FGM": "fgm",
    "FGA": "fga",
    "FTM": "ftm",
    "FTA": "fta",
    "OREB": "oreb",
    "DREB": "dreb",
    "PF": "pf",
}

# Used only until the league's settings page is imported (Yahoo's default points scoring).
DEFAULT_WEIGHTS = {"PTS": 1.0, "REB": 1.2, "AST": 1.5, "ST": 3.0, "BLK": 3.0, "TO": -1.0, "3PTM": 0.5}


def league_weights(league: League | None) -> tuple[dict[str, float], bool]:
    """Scoring weights keyed by GameLog column, and whether they came from the league's settings."""
    scoring = None
    if league and league.settings_json:
        scoring = json.loads(league.settings_json).get("scoring")
    from_settings = bool(scoring)
    weights: dict[str, float] = {}
    for abbr, w in (scoring or DEFAULT_WEIGHTS).items():
        col = YAHOO_TO_LOG.get(abbr)
        if col:
            weights[col] = weights.get(col, 0.0) + float(w)
    return weights, from_settings


def fantasy_points(log: GameLog, weights: dict[str, float]) -> float:
    return sum(getattr(log, col) * w for col, w in weights.items())
