"""Untouchable players: never suggested as drops (per league and team)."""

import json

from sqlalchemy.orm import Session

from app.db.models import AppSetting


def _key(league_id: int, team_id: int) -> str:
    return f"untouchable:{league_id}:{team_id}"


def get_untouchables(db: Session, league_id: int, team_id: int) -> set[int]:
    row = db.get(AppSetting, _key(league_id, team_id))
    try:
        return {int(x) for x in json.loads(row.value)} if row and row.value else set()
    except (ValueError, TypeError):
        return set()


def set_untouchables(db: Session, league_id: int, team_id: int, ids: set[int]) -> None:
    key = _key(league_id, team_id)
    row = db.get(AppSetting, key) or AppSetting(key=key)
    row.value = json.dumps(sorted(ids))
    db.add(row)
    db.commit()
