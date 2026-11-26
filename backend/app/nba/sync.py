"""Refresh NBA data into the database: schedule, players, and finished-game box scores."""

import logging
import threading
from datetime import UTC, datetime

from sqlalchemy import delete

from app.db import SessionLocal
from app.db.models import AppSetting, GameLog, NbaGame, NbaPlayer
from app.nba import client

log = logging.getLogger(__name__)
_lock = threading.Lock()

# Yahoo and NBA mostly share team codes; these cover the usual alternatives.
TEAM_ALIASES = {"PHO": "PHX", "GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "BRK": "BKN", "CHO": "CHA", "WSH": "WAS"}


def norm_team(code: str | None) -> str | None:
    if not code:
        return None
    code = code.upper()
    return TEAM_ALIASES.get(code, code)


def _parse_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        return None


def _set(db, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def refresh() -> dict:
    """Download and store fresh NBA data. Returns counts for display."""
    with _lock:
        sched = client.fetch_schedule()
        season = sched["seasonYear"]
        games = []
        for day in sched["gameDates"]:
            for g in day["games"]:
                home, away = g["homeTeam"].get("teamTricode"), g["awayTeam"].get("teamTricode")
                if not home or not away:  # knockout games whose teams aren't decided yet
                    continue
                gid = str(g["gameId"])
                games.append(
                    NbaGame(
                        id=gid,
                        date_et=g["gameDateEst"][:10],
                        start_utc=_parse_utc(g.get("gameDateTimeUTC")),
                        home=home,
                        away=away,
                        status=int(g.get("gameStatus") or 1),
                        # Regular season games (incl. NBA Cup group/knockout games) start with 002.
                        # Preseason (001) and the Cup final (006) don't count for fantasy.
                        regular_season=1 if gid.startswith("002") else 0,
                    )
                )

        logs = client.fetch_game_logs(season)
        players = client.fetch_players(season)
        try:  # positions are a nice-to-have: don't fail the refresh without them
            positions = {int(r["PERSON_ID"]): r.get("POSITION") or None for r in client.fetch_player_index(season)}
        except Exception as e:
            log.warning("NBA positions unavailable: %s", e)
            positions = {}
        # The schedule file updates game status slowly; a result (W/L) in the box scores means it's over.
        finished = {g.id for g in games if g.status == 3} | {str(r["GAME_ID"]) for r in logs if r.get("WL")}
        for g in games:
            if g.id in finished:
                g.status = 3

        with SessionLocal() as db:
            db.execute(delete(NbaGame))
            db.add_all(games)

            db.execute(delete(NbaPlayer))
            seen: set[int] = set()
            for p in players:
                pid = int(p["PERSON_ID"])
                seen.add(pid)
                db.add(NbaPlayer(id=pid, name=p["DISPLAY_FIRST_LAST"], team=p.get("TEAM_ABBREVIATION") or None, position=positions.get(pid)))

            db.execute(delete(GameLog))
            kept = 0
            for r in logs:
                gid = str(r["GAME_ID"])
                # Only finished games: lines for games in progress are incomplete.
                if gid not in finished and r.get("WL") is None:
                    continue
                pid = int(r["PLAYER_ID"])
                if pid not in seen:  # played this season but no longer listed (waived etc.)
                    seen.add(pid)
                    db.add(NbaPlayer(id=pid, name=r["PLAYER_NAME"], team=r.get("TEAM_ABBREVIATION"), position=positions.get(pid)))
                db.add(
                    GameLog(
                        player_id=pid,
                        game_id=gid,
                        date_et=str(r["GAME_DATE"])[:10],
                        team=r.get("TEAM_ABBREVIATION"),
                        min=float(r["MIN"] or 0),
                        pts=r["PTS"] or 0,
                        reb=r["REB"] or 0,
                        ast=r["AST"] or 0,
                        stl=r["STL"] or 0,
                        blk=r["BLK"] or 0,
                        tov=r["TOV"] or 0,
                        fg3m=r["FG3M"] or 0,
                        fgm=r["FGM"] or 0,
                        fga=r["FGA"] or 0,
                        ftm=r["FTM"] or 0,
                        fta=r["FTA"] or 0,
                        oreb=r["OREB"] or 0,
                        dreb=r["DREB"] or 0,
                        pf=r["PF"] or 0,
                    )
                )
                kept += 1
            now = datetime.now(UTC).replace(tzinfo=None)
            _set(db, "nba_refreshed_at", now.isoformat())
            _set(db, "nba_season", season)
            db.commit()

        from app.nba.matching import match_all

        unmatched = match_all()
        result = {"season": season, "games": len(games), "game_logs": kept, "players": len(seen), "unmatched": unmatched}
        log.info("NBA data refreshed: %s", result)
        return result


# ------------------------------------------------------------------ background refresh

REFRESH_EVERY_HOURS = 3
_bg: threading.Thread | None = None
_bg_stop = threading.Event()
last_error: str | None = None


def refreshed_at() -> datetime | None:
    with SessionLocal() as db:
        row = db.get(AppSetting, "nba_refreshed_at")
        return datetime.fromisoformat(row.value) if row and row.value else None


def _loop() -> None:
    global last_error
    while not _bg_stop.is_set():
        at = refreshed_at()
        age_h = (datetime.now(UTC).replace(tzinfo=None) - at).total_seconds() / 3600 if at else None
        if age_h is None or age_h >= REFRESH_EVERY_HOURS:
            try:
                refresh()
                last_error = None
            except Exception as e:  # network problems shouldn't stop the app
                last_error = str(e)
                log.warning("NBA refresh failed: %s", e)
        _bg_stop.wait(15 * 60)


def start_background() -> None:
    global _bg
    if _bg and _bg.is_alive():
        return
    _bg_stop.clear()
    _bg = threading.Thread(target=_loop, daemon=True, name="nba-refresh")
    _bg.start()


def stop_background() -> None:
    _bg_stop.set()
