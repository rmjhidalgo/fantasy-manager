"""Per-player projections: expected fantasy points per game, spread, and chance of playing.

Method (kept simple and explainable):
- FP per game = weighted blend of the player's averages over the last 7, 14, 30 days
  and the whole season, each window counting less when it has few games.
  Recent windows carry the minutes trend (a bigger or smaller role shows up there first).
- Spread (standard deviation) from the player's game-to-game results.
- Chance of playing from the injury tag on the latest imported Yahoo page,
  slightly lower on the second night of a back-to-back.
- No NBA games yet (or no NBA match): Yahoo's own season average, if imported.
"""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GameLog, League, Player, PlayerMap, PlayerStats
from app.engine.scoring import fantasy_points, league_weights

# window length in days (None = season) -> (weight, games needed for full weight)
WINDOWS: list[tuple[int | None, float, int]] = [(7, 0.15, 3), (14, 0.25, 5), (30, 0.30, 8), (None, 0.30, 10)]

# Yahoo injury tag -> chance the player plays a given game
PLAY_PROBABILITY = {
    None: 0.97,  # healthy players still sit now and then
    "P": 0.90,
    "Q": 0.60,
    "GTD": 0.60,
    "D": 0.25,
    "O": 0.0,
    "INJ": 0.0,
    "OFS": 0.0,
    "NA": 0.0,
    "SUSP": 0.0,
}
BACK_TO_BACK_FACTOR = 0.95


@dataclass
class Projection:
    yahoo_id: int
    name: str
    nba_team: str | None
    positions: list[str]
    status: str | None
    fpts: float  # expected FP when he plays
    sd: float
    play_prob: float
    games_used: int
    source: str  # "nba" | "yahoo" | "none"
    recent_mpg: float | None = None
    season_mpg: float | None = None

    def play_prob_on(self, b2b: bool) -> float:
        return self.play_prob * (BACK_TO_BACK_FACTOR if b2b else 1.0)


def _blend(values_by_window: list[list[float]]) -> float | None:
    num = den = 0.0
    for (_, weight, full), vals in zip(WINDOWS, values_by_window, strict=True):
        if not vals:
            continue
        w = weight * min(1.0, len(vals) / full)
        num += w * statistics.fmean(vals)
        den += w
    return num / den if den else None


def project_players(db: Session, league: League, yahoo_ids: list[int], today: date) -> dict[int, Projection]:
    weights, _ = league_weights(league)
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(yahoo_ids)))}
    maps = {m.yahoo_id: m.nba_id for m in db.scalars(select(PlayerMap).where(PlayerMap.yahoo_id.in_(yahoo_ids)))}
    nba_ids = [n for n in maps.values() if n]
    logs_by_player: dict[int, list[GameLog]] = {}
    for g in db.scalars(select(GameLog).where(GameLog.player_id.in_(nba_ids), GameLog.date_et < today.isoformat())):
        logs_by_player.setdefault(g.player_id, []).append(g)
    yahoo_stats = {
        s.player_id: s
        for s in db.scalars(select(PlayerStats).where(PlayerStats.league_id == league.id, PlayerStats.player_id.in_(yahoo_ids)))
        if s.window.startswith("S_AS")
    }

    out: dict[int, Projection] = {}
    for yid in yahoo_ids:
        p = players.get(yid)
        if p is None:
            continue
        logs = sorted(logs_by_player.get(maps.get(yid) or -1, []), key=lambda g: g.date_et)
        fp = [fantasy_points(g, weights) for g in logs]
        mins = [g.min or 0 for g in logs]
        status = p.status or None
        prob = PLAY_PROBABILITY.get(status, 0.6)
        positions = [x for x in (p.positions or "").split(",") if x]

        if fp:
            per_window = []
            for days, _, _ in WINDOWS:
                cutoff = (today - timedelta(days=days)).isoformat() if days else ""
                per_window.append([v for v, g in zip(fp, logs, strict=True) if g.date_et >= cutoff])
            mean = _blend(per_window) or 0.0
            recent = fp[-15:]
            sd = statistics.pstdev(recent) if len(recent) >= 3 else 0.35 * mean
            last14 = [m for m, g in zip(mins, logs, strict=True) if g.date_et >= (today - timedelta(days=14)).isoformat()]
            out[yid] = Projection(
                yid, p.name, p.nba_team, positions, status, round(mean, 2), round(max(sd, 4.0), 2), prob, len(fp), "nba",
                recent_mpg=round(statistics.fmean(last14), 1) if last14 else None,
                season_mpg=round(statistics.fmean(mins), 1),
            )
        elif yid in yahoo_stats and yahoo_stats[yid].fpts is not None:
            mean = yahoo_stats[yid].fpts
            out[yid] = Projection(yid, p.name, p.nba_team, positions, status, mean, max(0.35 * mean, 4.0), prob, yahoo_stats[yid].gp or 0, "yahoo")
        else:
            out[yid] = Projection(yid, p.name, p.nba_team, positions, status, 0.0, 4.0, prob, 0, "none")
    return out
