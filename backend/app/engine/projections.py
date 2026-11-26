"""Per-player projections: expected fantasy points per game, spread, and chance of playing.

Method (kept simple and explainable):
- FP per game = weighted blend of the player's averages over the last 7, 14, 30 days
  and the whole season, each window counting less when it has few games.
  Recent windows carry the minutes trend (a bigger or smaller role shows up there first).
- Spread (standard deviation) from the player's game-to-game results.
- Chance of playing from the injury tag on the latest imported Yahoo page,
  slightly lower on the second night of a back-to-back.
  A player with no tag who has missed his team's last 3+ games is treated as doubtful:
  tags on saved pages can be out of date, box scores aren't.
- Injured players on ESPN's injury list (refreshed with the NBA data) have an expected
  return date: they count as out (or 50% if day-to-day) until then, and 90% from then on.
  That list wins over a Yahoo tag, since it's newer.
- No NBA games yet (or no NBA match): Yahoo's own season average, if imported.

Players who aren't on any saved Yahoo page (worked out as available from NBA data) are
projected the same way. Their positions come from NBA.com and are only an estimate of
Yahoo's eligibility.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GameLog, League, NbaGame, NbaInjury, NbaPlayer, Player, PlayerMap, PlayerStats
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
# Injury with an expected return date (ESPN): chance of playing before that day, and from it on
INJURY_BEFORE_RETURN = {"Out": 0.0, "Day-To-Day": 0.5}
PROB_AFTER_RETURN = 0.9  # first weeks back: some rest days and setbacks
ABSENT_GAMES = 3  # missed this many team games in a row without a tag -> treat as doubtful
ABSENT_PROBABILITY = 0.3

# NBA.com position -> likely Yahoo eligibility
NBA_POSITIONS = {
    "G": ["PG", "SG"],
    "F": ["SF", "PF"],
    "C": ["C"],
    "G-F": ["SG", "SF"],
    "F-G": ["SG", "SF"],
    "F-C": ["PF", "C"],
    "C-F": ["PF", "C"],
}


def virtual_id(nba_id: int) -> int:
    """Id for a player known only from NBA data (no Yahoo id): negative, so it never clashes."""
    return -nba_id


@dataclass
class Projection:
    yahoo_id: int  # Yahoo player id, or virtual_id(nba_id) for players not on any saved page
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
    nba_id: int | None = None
    positions_estimated: bool = False
    missed_streak: int = 0  # team games missed in a row, most recent first
    window_fp: dict[str, float | None] = field(default_factory=dict)  # L7 / L14 / L30 / S averages
    # Injury with an expected return (ESPN injury list): chance of playing before / from that day
    return_date: date | None = None
    injury: dict | None = None  # {status, return_date, injury, comment, reported}
    prob_before_return: float | None = None
    prob_after_return: float | None = None

    def play_prob_on(self, b2b: bool, day: date | None = None) -> float:
        """Chance he plays on a given day (default: today's status). Knows the expected return of an injury."""
        p = self.play_prob
        if self.return_date is not None and day is not None:
            p = self.prob_before_return if day < self.return_date else self.prob_after_return
        return p * (BACK_TO_BACK_FACTOR if b2b else 1.0)

    def available_from(self) -> date | None:
        """First day he's expected to be able to play again, if he's out with a known return."""
        return self.return_date if self.return_date is not None and self.prob_before_return == 0 else None


def injury_text(p: Projection, today: date) -> str | None:
    """'Out until about Jan 2 (Knee - Patellar tendon tear)' for players with a known expected return."""
    if not p.injury or p.return_date is None or p.return_date <= today:
        return None
    what = f" ({p.injury['injury']})" if p.injury.get("injury") else ""
    when = f"{p.return_date:%b} {p.return_date.day}"
    if p.injury.get("status") == "Day-To-Day":
        return f"Day-to-day until about {when}{what}"
    return f"Out until about {when}{what}"


def load_windows(db: Session) -> list[tuple[int | None, float, int]]:
    """The window weights in use: tuned ones (Settings → Projection tuning) or the defaults."""
    import json

    from app.db.models import AppSetting

    row = db.get(AppSetting, "projection_weights")
    try:
        w = json.loads(row.value) if row and row.value else None
    except ValueError:
        w = None
    if not w or len(w) != len(WINDOWS):
        return WINDOWS
    return [(days, float(x), full) for (days, _, full), x in zip(WINDOWS, w, strict=True)]


def _blend(values_by_window: list[list[float]], windows: list[tuple[int | None, float, int]] = WINDOWS) -> float | None:
    num = den = 0.0
    for (_, weight, full), vals in zip(windows, values_by_window, strict=True):
        if not vals:
            continue
        w = weight * min(1.0, len(vals) / full)
        num += w * statistics.fmean(vals)
        den += w
    return num / den if den else None


class _Context:
    """Data shared by all projections in one call."""

    def __init__(self, db: Session, league: League, nba_ids: list[int], today: date):
        self.today = today
        self.weights, _ = league_weights(league)
        self.windows = load_windows(db)
        self.logs: dict[int, list[GameLog]] = defaultdict(list)
        for g in db.scalars(select(GameLog).where(GameLog.player_id.in_(nba_ids), GameLog.date_et < today.isoformat())):
            self.logs[g.player_id].append(g)
        for v in self.logs.values():
            v.sort(key=lambda g: g.date_et)
        # Each team's finished games, most recent first
        self.team_games: dict[str, list[str]] = defaultdict(list)
        for g in db.scalars(
            select(NbaGame)
            .where(NbaGame.status == 3, NbaGame.regular_season == 1, NbaGame.date_et < today.isoformat())
            .order_by(NbaGame.date_et.desc())
        ):
            self.team_games[g.home].append(g.id)
            self.team_games[g.away].append(g.id)
        # Injured players with an expected return date
        self.injuries: dict[int, NbaInjury] = {
            i.nba_id: i for i in db.scalars(select(NbaInjury).where(NbaInjury.nba_id.in_(nba_ids))) if i.nba_id
        }

    def missed_streak(self, team: str | None, logs: list[GameLog]) -> int:
        if not team:
            return 0
        played = {g.game_id for g in logs}
        n = 0
        for gid in self.team_games.get(team, [])[:15]:
            if gid in played:
                break
            n += 1
        return n

    def build(self, pid: int, name: str, team: str | None, positions: list[str], status: str | None, nba_id: int | None,
              yahoo_fpts: tuple[float, int] | None = None, positions_estimated: bool = False) -> Projection:
        logs = self.logs.get(nba_id, []) if nba_id else []
        prob = PLAY_PROBABILITY.get(status, 0.6)
        missed = self.missed_streak(team, logs) if logs else 0
        if status is None and missed >= ABSENT_GAMES:
            prob = ABSENT_PROBABILITY
        common = dict(nba_id=nba_id, positions_estimated=positions_estimated, missed_streak=missed)
        inj = self.injuries.get(nba_id) if nba_id else None
        if inj is not None and inj.return_date:
            # ESPN's list is refreshed every few hours, so it beats a Yahoo tag saved earlier
            ret = date.fromisoformat(inj.return_date)
            before = INJURY_BEFORE_RETURN.get(inj.status, 0.0)
            common.update(return_date=ret, prob_before_return=before, prob_after_return=PROB_AFTER_RETURN,
                          injury={"status": inj.status, "return_date": inj.return_date, "injury": inj.injury,
                                  "comment": inj.comment, "reported": inj.reported})
            prob = before if self.today < ret else PROB_AFTER_RETURN
        if logs:
            fp = [fantasy_points(g, self.weights) for g in logs]
            per_window, window_fp = [], {}
            for days, _, _ in self.windows:
                cutoff = (self.today - timedelta(days=days)).isoformat() if days else ""
                vals = [v for v, g in zip(fp, logs, strict=True) if g.date_et >= cutoff]
                per_window.append(vals)
                window_fp[f"L{days}" if days else "S"] = round(statistics.fmean(vals), 1) if vals else None
            mean = _blend(per_window, self.windows) or 0.0
            recent = fp[-15:]
            sd = statistics.pstdev(recent) if len(recent) >= 3 else 0.35 * mean
            cutoff14 = (self.today - timedelta(days=14)).isoformat()
            last14 = [g.min or 0 for g in logs if g.date_et >= cutoff14]
            return Projection(
                pid, name, team, positions, status, round(mean, 2), round(max(sd, 4.0), 2), prob, len(fp), "nba",
                recent_mpg=round(statistics.fmean(last14), 1) if last14 else None,
                season_mpg=round(statistics.fmean([g.min or 0 for g in logs]), 1),
                window_fp=window_fp, **common,
            )
        if yahoo_fpts is not None:
            mean, gp = yahoo_fpts
            return Projection(pid, name, team, positions, status, mean, max(0.35 * mean, 4.0), prob, gp, "yahoo",
                              window_fp={"S": mean}, **common)
        return Projection(pid, name, team, positions, status, 0.0, 4.0, prob, 0, "none", **common)


def project_players(db: Session, league: League, yahoo_ids: list[int], today: date) -> dict[int, Projection]:
    """Projections for Yahoo players (ids from saved pages)."""
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(yahoo_ids)))}
    maps = {m.yahoo_id: m.nba_id for m in db.scalars(select(PlayerMap).where(PlayerMap.yahoo_id.in_(yahoo_ids)))}
    ctx = _Context(db, league, [n for n in maps.values() if n], today)
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
        ys = yahoo_stats.get(yid)
        out[yid] = ctx.build(
            yid, p.name, p.nba_team, [x for x in (p.positions or "").split(",") if x], p.status or None, maps.get(yid),
            yahoo_fpts=(ys.fpts, ys.gp or 0) if ys and ys.fpts is not None else None,
        )
    return out


def project_nba_players(db: Session, league: League, nba_ids: list[int], today: date) -> dict[int, Projection]:
    """Projections for players known only from NBA data, keyed by virtual_id(nba_id)."""
    ctx = _Context(db, league, nba_ids, today)
    out: dict[int, Projection] = {}
    for p in db.scalars(select(NbaPlayer).where(NbaPlayer.id.in_(nba_ids))):
        positions = NBA_POSITIONS.get(p.position or "", ["PG", "SG", "SF", "PF", "C"] if not p.position else [])
        vid = virtual_id(p.id)
        out[vid] = ctx.build(vid, p.name, p.team, positions, None, p.id, positions_estimated=True)
    return out
