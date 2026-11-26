"""Projection tuning: learn the best mix of recent and season-long form from real results.

Backtest: for every game played in the last few weeks, project the player the way the app
would have the day before (only games before that day), then compare with what he
actually scored. Each candidate mix of the last 7 / 14 / 30 days and the season is scored
by its average miss (mean absolute error, in fantasy points). The best one can be applied;
projections then use it everywhere.
"""

import json
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppSetting, GameLog, League
from app.engine.projections import WINDOWS, _blend, load_windows
from app.engine.schedule import today_et
from app.engine.scoring import fantasy_points, league_weights

CANDIDATES: dict[str, list[float]] = {
    "Standard": [0.15, 0.25, 0.30, 0.30],
    "More recent": [0.25, 0.30, 0.25, 0.20],
    "Hot hand": [0.40, 0.30, 0.20, 0.10],
    "More season": [0.05, 0.15, 0.30, 0.50],
    "Even": [0.25, 0.25, 0.25, 0.25],
}
MIN_PRIOR_GAMES = 5
MIN_IMPROVEMENT = 0.01  # recommend a change only if it misses at least 1% less


def _windows(weights: list[float]) -> list[tuple[int | None, float, int]]:
    return [(d, w, full) for (d, _, full), w in zip(WINDOWS, weights, strict=True)]


def backtest(db: Session, league: League, days: int = 21, now_utc: datetime | None = None) -> dict:
    today = today_et(now_utc)
    start = today - timedelta(days=days)
    weights, _ = league_weights(league)
    logs: dict[int, list[GameLog]] = defaultdict(list)
    for g in db.scalars(select(GameLog).where(GameLog.date_et < today.isoformat())):
        logs[g.player_id].append(g)

    errors: dict[str, list[float]] = {k: [] for k in CANDIDATES}
    current = [w for _, w, _ in load_windows(db)]
    candidates = dict(CANDIDATES)
    if current not in candidates.values():
        candidates["Current (tuned)"] = current
        errors["Current (tuned)"] = []
    tests = 0
    for games in logs.values():
        games.sort(key=lambda g: g.date_et)
        dates = [g.date_et for g in games]
        fp = [fantasy_points(g, weights) for g in games]
        for k, g in enumerate(games):
            if g.date_et < start.isoformat() or k < MIN_PRIOR_GAMES or (g.min or 0) <= 0:
                continue
            day = date.fromisoformat(g.date_et)
            per_window = []
            for d, _, _ in WINDOWS:
                lo = bisect_left(dates, (day - timedelta(days=d)).isoformat()) if d else 0
                per_window.append(fp[lo:k])
            tests += 1
            for name, w in candidates.items():
                pred = _blend(per_window, _windows(w))
                if pred is not None:
                    errors[name].append(abs(pred - fp[k]))

    results = [{"name": n, "weights": candidates[n], "mae": round(statistics.fmean(e), 3) if e else None, "games": len(e)}
               for n, e in errors.items()]
    results.sort(key=lambda r: (r["mae"] is None, r["mae"]))
    in_use = next((r for r in results if r["weights"] == current), None)
    best = results[0] if results and results[0]["mae"] is not None else None
    recommend = (best is not None and in_use is not None and best["weights"] != current
                 and best["mae"] < in_use["mae"] * (1 - MIN_IMPROVEMENT))
    return {
        "days": days, "games_tested": tests, "results": results, "current": current,
        "best": best, "recommend": recommend,
        "windows": ["Last 7 days", "Last 14 days", "Last 30 days", "Season"],
    }


def apply_weights(db: Session, weights: list[float] | None) -> list[float]:
    """Use these window weights for all projections (None = back to the defaults)."""
    row = db.get(AppSetting, "projection_weights") or AppSetting(key="projection_weights")
    row.value = json.dumps(weights) if weights else None
    db.add(row)
    row2 = db.get(AppSetting, "projection_weights_at") or AppSetting(key="projection_weights_at")
    row2.value = datetime.now(UTC).replace(tzinfo=None).isoformat() if weights else None
    db.add(row2)
    db.commit()
    return [w for _, w, _ in load_windows(db)]
