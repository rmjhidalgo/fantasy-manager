"""Daily lineup optimizer.

For one day: among the roster's players who have a game, fill the league's active
slots (PG, SG, G, SF, PF, F, C, C, Util, Util, ...) to get the most expected
fantasy points. Expected points = chance of playing x projected FP. This is an
assignment problem, solved exactly with scipy's linear_sum_assignment.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

# Which player positions may fill which slot.
SLOT_ACCEPTS: dict[str, set[str]] = {
    "PG": {"PG"},
    "SG": {"SG"},
    "G": {"PG", "SG"},
    "SF": {"SF"},
    "PF": {"PF"},
    "F": {"SF", "PF"},
    "C": {"C"},
    "Util": {"PG", "SG", "SF", "PF", "C"},
}
INACTIVE_SLOTS = {"BN", "IL", "IL+", "NA"}

DEFAULT_ACTIVE_SLOTS = ["PG", "SG", "G", "SF", "PF", "F", "C", "C", "Util", "Util"]


def active_slots(roster_positions: list[str] | None) -> list[str]:
    slots = [s for s in (roster_positions or []) if s not in INACTIVE_SLOTS]
    return slots or DEFAULT_ACTIVE_SLOTS


def eligible(slot: str, positions: list[str]) -> bool:
    return bool(SLOT_ACCEPTS.get(slot, set()) & set(positions))


@dataclass
class Candidate:
    player_id: int
    positions: list[str]
    value: float  # expected fantasy points today


@dataclass
class DayLineup:
    assignments: dict[int, str]  # player_id -> slot
    expected: float
    bench_with_game: list[int] = field(default_factory=list)  # had a game but no slot left


def optimize_day(slots: list[str], candidates: list[Candidate]) -> DayLineup:
    cands = [c for c in candidates if c.value > 0]
    if not cands or not slots:
        return DayLineup({}, 0.0, [c.player_id for c in cands])
    big = 1e6
    cost = np.full((len(cands), len(slots)), big)
    for i, c in enumerate(cands):
        for j, s in enumerate(slots):
            if eligible(s, c.positions):
                cost[i, j] = -c.value
    rows, cols = linear_sum_assignment(cost)
    assignments: dict[int, str] = {}
    total = 0.0
    for i, j in zip(rows, cols, strict=True):
        if cost[i, j] < big:
            assignments[cands[i].player_id] = slots[j]
            total += cands[i].value
    bench = [c.player_id for c in cands if c.player_id not in assignments]
    return DayLineup(assignments, total, bench)
