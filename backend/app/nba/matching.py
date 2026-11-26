"""Link Yahoo players to NBA players (names + team).

Order of attempts, first unique hit wins:
1. same normalised full name and same team
2. same normalised full name (any team: covers trades not yet reflected)
3. same last name + first initial and same team
Manual links (method "manual" / "none") are never changed automatically.
"""

import re
import unicodedata
from collections import defaultdict

from sqlalchemy import select

from app.db import SessionLocal
from app.db.models import NbaPlayer, Player, PlayerMap

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’`-]", "", s)
    words = [w for w in s.split() if w not in _SUFFIXES]
    return " ".join(words)


def _initial_last(n: str) -> str | None:
    words = n.split()
    return f"{words[0][0]} {words[-1]}" if len(words) >= 2 else None


def match_new() -> int:
    """Match Yahoo players that have no link yet (e.g. just imported from a saved page), leaving existing links alone.
    Without NBA data yet there's nothing to match against; the next NBA download does it."""
    return match_all(only_new=True)


def match_all(only_new: bool = False) -> int:
    """(Re)match every Yahoo player without a manual link. Returns how many remain unmatched."""
    from app.nba.sync import norm_team

    with SessionLocal() as db:
        nba = db.scalars(select(NbaPlayer)).all()
        if only_new and not nba:
            return 0
        by_name: dict[str, list[NbaPlayer]] = defaultdict(list)
        by_initial: dict[str, list[NbaPlayer]] = defaultdict(list)
        for p in nba:
            n = norm_name(p.name)
            by_name[n].append(p)
            key = _initial_last(n)
            if key:
                by_initial[key].append(p)

        keep = select(PlayerMap) if only_new else select(PlayerMap).where(PlayerMap.method != "auto")
        manual = {m.yahoo_id for m in db.scalars(keep)}
        unmatched = 0
        for yp in db.scalars(select(Player)).all():
            if yp.id in manual:
                continue
            n = norm_name(yp.name)
            team = norm_team(yp.nba_team)
            found = None
            cands = by_name.get(n, [])
            same_team = [c for c in cands if c.team == team]
            if len(same_team) == 1:
                found = same_team[0]
            elif len(cands) == 1:
                found = cands[0]
            else:
                key = _initial_last(n)
                cands = [c for c in by_initial.get(key, []) if c.team == team] if key else []
                if len(cands) == 1:
                    found = cands[0]
            row = db.get(PlayerMap, yp.id)
            if found:
                if row is None:
                    db.add(PlayerMap(yahoo_id=yp.id, nba_id=found.id, method="auto"))
                else:
                    row.nba_id, row.method = found.id, "auto"
            else:
                unmatched += 1
                if row is not None:
                    db.delete(row)
        db.commit()
        return unmatched


def candidates(yahoo_name: str, limit: int = 8) -> list[NbaPlayer]:
    """NBA players whose last name matches, for the manual-fix list."""
    n = norm_name(yahoo_name)
    last = n.split()[-1] if n else ""
    with SessionLocal() as db:
        out = [p for p in db.scalars(select(NbaPlayer)).all() if norm_name(p.name).split()[-1:] == [last]]
    return out[:limit]
