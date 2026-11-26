"""How many points a roster puts in the lineup over a run of days.

The free agent finder and the streaming planner both ask the same question: "if my
roster were these players on these days, how many points would my best lineups score?"
This answers it with the lineup optimizer, day by day, remembering results because the
same day/roster combinations come up again and again.
"""

from collections.abc import Iterable
from datetime import date, datetime

from app.engine.lineup import Candidate, optimize_day
from app.engine.projections import Projection
from app.engine.schedule import Schedule


class LineupValue:
    def __init__(self, slots: list[str], sched: Schedule, days: list[date], proj: dict[int, Projection],
                 now_utc: datetime, today: date):
        self.slots = slots
        self.sched = sched
        self.days = days
        self.proj = proj
        self.now = now_utc
        self.today = today
        self._vals: dict[int, list[float]] = {}
        self._memo: dict[tuple[int, frozenset[int]], float] = {}

    def has_open_game(self, pid: int, i: int) -> bool:
        """A game on day i that hasn't started yet."""
        p = self.proj.get(pid)
        d = self.days[i]
        g = self.sched.game(p.nba_team, d) if p else None
        if g is None:
            return False
        return not (d == self.today and (g.status != 1 or (g.start_utc is not None and g.start_utc <= self.now)))

    def values(self, pid: int) -> list[float]:
        """Expected points for each day, if he's in the lineup (0 without a game, or once his game has started)."""
        if pid not in self._vals:
            p = self.proj.get(pid)
            self._vals[pid] = [
                p.play_prob_on(self.sched.is_back_to_back(p.nba_team, d)) * p.fpts if self.has_open_game(pid, i) else 0.0
                for i, d in enumerate(self.days)
            ]
        return self._vals[pid]

    def games(self, pid: int, start: int = 0, end: int | None = None) -> int:
        """Games still to play from day index start to end (exclusive)."""
        stop = len(self.days) if end is None else end
        return sum(1 for i in range(start, stop) if self.has_open_game(pid, i))

    def day_total(self, i: int, pids: Iterable[int]) -> float:
        key = (i, frozenset(p for p in pids if self.values(p)[i] > 0))
        if key not in self._memo:
            cands = [Candidate(p, self.proj[p].positions, self.values(p)[i]) for p in key[1]]
            self._memo[key] = optimize_day(self.slots, cands).expected
        return self._memo[key]

    def total(self, timeline: list[set[int]]) -> float:
        """timeline[i] = the players on the roster on day i."""
        return sum(self.day_total(i, ids) for i, ids in enumerate(timeline))

    def first_day_index(self, available_from: date | None) -> int | None:
        """Index of the first day a player can be used, or None if not within these days."""
        if available_from is None:
            return 0
        for i, d in enumerate(self.days):
            if d >= available_from:
                return i
        return None
