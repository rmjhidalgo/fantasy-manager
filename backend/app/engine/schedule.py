"""NBA schedule helpers: dates in US Eastern time (the dates Yahoo uses), games per team."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NbaGame

ET = ZoneInfo("America/New_York")


def today_et(now_utc: datetime | None = None) -> date:
    now = (now_utc or datetime.now(UTC).replace(tzinfo=None)).replace(tzinfo=UTC)
    return now.astimezone(ET).date()


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


class Schedule:
    """Regular-season games between two dates, indexed by team and date."""

    def __init__(self, db: Session, start: date, end: date):
        rows = db.scalars(
            select(NbaGame).where(
                NbaGame.regular_season == 1,
                NbaGame.date_et >= start.isoformat(),
                NbaGame.date_et <= end.isoformat(),
            )
        ).all()
        self.games = rows
        self.by_team_date: dict[tuple[str, str], NbaGame] = {}
        self.dates_by_team: dict[str, list[str]] = defaultdict(list)
        for g in rows:
            for team in (g.home, g.away):
                self.by_team_date[(team, g.date_et)] = g
                self.dates_by_team[team].append(g.date_et)

    def game(self, team: str | None, day: date) -> NbaGame | None:
        return self.by_team_date.get((team, day.isoformat())) if team else None

    def is_back_to_back(self, team: str | None, day: date) -> bool:
        """Second night of a back-to-back (the team also played the day before)."""
        return team is not None and (team, (day - timedelta(days=1)).isoformat()) in self.by_team_date
