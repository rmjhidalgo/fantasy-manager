"""Streaming planner: a chain of add/drops for the rest of the week, within your remaining adds.

Greedy and explainable: at each step it tries every (day, player to add, player to drop)
and keeps the move that adds the most points to your lineups over the rest of the week,
then repeats with the moves chosen so far in place. A streamer added earlier in the chain
can be dropped again later ("add X today, drop X Thursday for Y"). It stops when the adds
run out or nothing gains at least MIN_GAIN points. Your own players are dropped only for
someone about as good per game, so a stream never costs you long-term value.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import League
from app.engine.freeagents import TeamContext, build_context

MIN_GAIN = 2.0
# A regular roster player is only dropped for someone projected at least this close per game
# (streamers added earlier in the chain can always be dropped).
KEEP_TOLERANCE = 1.5
CANDIDATES = 30  # available players considered (best by raw points over the week)


@dataclass
class StreamMove:
    day_index: int
    add: int
    drop: int | None
    gain: float


def plan_streams(ctx: TeamContext, adds_left: int, min_gain: float = MIN_GAIN) -> tuple[list[StreamMove], float, float]:
    lv = ctx.lv
    n = len(ctx.days)
    timeline = [set(ctx.active_ids) for _ in range(n)]
    baseline = lv.total(timeline)
    if n == 0 or adds_left <= 0:
        return [], baseline, baseline

    starts = {}
    raw = []
    for pp in ctx.pool:
        if pp.id not in ctx.proj:
            continue
        s = lv.first_day_index(ctx.available_from(pp))
        if s is None:
            continue
        starts[pp.id] = s
        raw.append((sum(lv.values(pp.id)[s:]), pp.id))
    cands = [pid for v, pid in sorted(raw, reverse=True)[:CANDIDATES] if v > 0]

    droppable = set(ctx.droppable())
    capacity = ctx.capacity
    moves: list[StreamMove] = []
    added: set[int] = set()
    dropped: set[int] = set()
    current = baseline
    for _ in range(adds_left):
        best: tuple[float, int, int, int | None, list[set[int]]] | None = None
        for day in range(n):
            roster_then = timeline[day]
            open_spot = len(roster_then) < capacity
            drop_options: list[int | None] = [None] if open_spot else sorted(((droppable | added) & roster_then) - dropped)
            for pid in cands:
                if pid in added or pid in dropped or day < starts[pid] or not lv.has_open_game(pid, day):
                    continue  # adding on a day he doesn't play wastes that day: add on a game day instead
                for drop in drop_options:
                    if drop is not None and drop not in added and ctx.proj[pid].fpts < ctx.proj[drop].fpts - KEEP_TOLERANCE:
                        continue  # don't give up a better player for the rest of the season just for this week
                    tl =[s if i < day else (s - {drop}) | {pid} for i, s in enumerate(timeline)]
                    gain = lv.total(tl) - current
                    if best is None or gain > best[0] + 1e-9:
                        best = (gain, day, pid, drop, tl)
        if best is None or best[0] < min_gain:
            break
        gain, day, pid, drop, tl = best
        moves.append(StreamMove(day, pid, drop, round(gain, 1)))
        added.add(pid)
        if drop is not None:
            dropped.add(drop)
            added.discard(drop)
        timeline = tl
        current += gain
    moves.sort(key=lambda m: m.day_index)
    return moves, baseline, current


def streaming_plan(db: Session, league: League, team_id: int, adds_left: int, now_utc: datetime | None = None) -> dict:
    ctx = build_context(db, league, team_id, "week", now_utc)
    moves, baseline, total = plan_streams(ctx, adds_left)
    pool = {pp.id: pp for pp in ctx.pool}
    lv = ctx.lv

    out = []
    for m in moves:
        # Days the added player stays: until a later move drops him, or the end of the week
        end = next((x.day_index for x in moves if x.drop == m.add and x.day_index > m.day_index), len(ctx.days))
        p = ctx.proj[m.add]
        pp = pool[m.add]
        out.append({
            "date": ctx.days[m.day_index].isoformat(),
            "add": {
                "id": m.add, "yahoo_id": pp.yahoo_id, "name": p.name, "nba_team": p.nba_team, "positions": p.positions,
                "positions_estimated": p.positions_estimated, "kind": pp.kind, "source": pp.source, "fpts": p.fpts,
                "status": p.status,
            },
            "drop": m.drop and {"id": m.drop, "name": ctx.proj[m.drop].name, "fpts": ctx.proj[m.drop].fpts},
            "drop_is_streamer": m.drop is not None and any(x.add == m.drop for x in moves),
            "games": lv.games(m.add, m.day_index, end),
            "game_dates": [ctx.days[i].isoformat() for i in range(m.day_index, end) if lv.has_open_game(m.add, i)],
            "gain": m.gain,
        })
    return {
        "days": [d.isoformat() for d in ctx.days],
        "window_label": ctx.window_label,
        "adds_left": adds_left,
        "baseline": round(baseline, 1),
        "with_moves": round(total, 1),
        "gain": round(total - baseline, 1),
        "moves": out,
        "open_spots": ctx.open_spots,
        "min_gain": MIN_GAIN,
        "keep_tolerance": KEEP_TOLERANCE,
    }
