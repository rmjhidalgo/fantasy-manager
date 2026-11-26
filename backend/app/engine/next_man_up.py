"""Next man up: which teammates got more minutes in the games an injured player missed."""

import statistics
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GameLog, League, NbaGame, NbaPlayer
from app.engine.scoring import fantasy_points, league_weights

MIN_MINUTES_GAIN = 4.0


@dataclass
class Beneficiary:
    nba_id: int
    name: str
    minutes_with: float  # average minutes when the injured player played
    minutes_without: float
    fpts_without: float
    games_without: int


def next_man_up(db: Session, league: League, nba_id: int, team: str, limit: int = 3) -> list[Beneficiary]:
    games = db.scalars(
        select(NbaGame)
        .where(NbaGame.status == 3, NbaGame.regular_season == 1, (NbaGame.home == team) | (NbaGame.away == team))
        .order_by(NbaGame.date_et.desc())
        .limit(20)
    ).all()
    game_ids = [g.id for g in games]
    logs = db.scalars(select(GameLog).where(GameLog.game_id.in_(game_ids), GameLog.team == team)).all()
    played = {g.game_id for g in logs if g.player_id == nba_id}
    missed = [gid for gid in game_ids if gid not in played]
    if not missed or not played:
        return []
    weights, _ = league_weights(league)
    by_player: dict[int, dict[str, list]] = {}
    for g in logs:
        if g.player_id == nba_id:
            continue
        d = by_player.setdefault(g.player_id, {"with": [], "without": [], "fp_without": []})
        if g.game_id in played:
            d["with"].append(g.min or 0)
        else:
            d["without"].append(g.min or 0)
            d["fp_without"].append(fantasy_points(g, weights))
    names = {p.id: p.name for p in db.scalars(select(NbaPlayer).where(NbaPlayer.id.in_(list(by_player))))}
    out = []
    for pid, d in by_player.items():
        if not d["without"]:
            continue
        # Didn't play when the injured player did = 0 minutes in those games (counts as a real increase)
        with_min = statistics.fmean(d["with"]) * len(d["with"]) / len(played) if d["with"] else 0.0
        without_min = statistics.fmean(d["without"]) * len(d["without"]) / len(missed)
        if without_min - with_min >= MIN_MINUTES_GAIN:
            out.append(Beneficiary(pid, names.get(pid, str(pid)), round(with_min, 1), round(without_min, 1),
                                   round(statistics.fmean(d["fp_without"]), 1), len(d["without"])))
    out.sort(key=lambda b: b.minutes_without - b.minutes_with, reverse=True)
    return out[:limit]
