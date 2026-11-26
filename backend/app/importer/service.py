"""Import a saved Yahoo page into the database.

Freshness rule: each kind of data (settings, standings, a team's roster, a matchup,
ownership and stats of each player) remembers the save time of the page it came
from. A page saved earlier than what's stored is skipped for that data, so
importing an old file never replaces newer information.
"""

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import config
from app.db import SessionLocal
from app.db.models import (
    AppSetting,
    FantasyTeam,
    ImportRecord,
    League,
    Matchup,
    Ownership,
    Player,
    PlayerStats,
    RosterSlot,
    ScheduleWeek,
    Transaction,
)
from app.importer import parsers as P
from app.importer.detect import PAGE_LABELS, PageKind, detect
from app.importer.source import NotAWebPage, read_page

_lock = threading.Lock()  # one import at a time (uploads and folder watch share the DB)


@dataclass
class ImportResult:
    filename: str
    status: str  # imported | partial | duplicate | unsupported | error
    page_type: str | None = None
    page_label: str | None = None
    league_id: int | None = None
    league_name: str | None = None
    saved_at: str | None = None  # ISO, UTC
    summary: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _newer(new: datetime | None, old: datetime | None) -> bool:
    """True if data saved at `new` may replace data saved at `old`."""
    return old is None or new is None or new >= old


# ------------------------------------------------------------------ public entry

def import_bytes(
    data: bytes,
    filename: str,
    source: str = "upload",
    fallback_saved_at: datetime | None = None,
) -> ImportResult:
    sha = hashlib.sha256(data).hexdigest()
    with _lock, SessionLocal() as db:
        if db.scalar(select(ImportRecord).where(ImportRecord.sha256 == sha, ImportRecord.status.in_(("imported", "partial")))):
            dup = ImportResult(filename, "duplicate", summary="Already imported, nothing new.")
            if source == "folder":  # the folder is re-scanned at every start: don't fill the history with these
                return dup
            return _record(db, sha, filename, source, None, None, dup)

        try:
            page = read_page(data, filename, fallback_saved_at)
        except NotAWebPage as e:
            return _record(db, sha, filename, source, None, None, ImportResult(filename, "unsupported", summary=str(e)))

        kind = detect(page.url)
        if kind is None:
            msg = "Not a Yahoo Fantasy Basketball page this app can read."
            if page.url:
                msg += f" (page address: {page.url})"
            return _record(db, sha, filename, source, page, None, ImportResult(filename, "unsupported", summary=msg))

        result = ImportResult(
            filename,
            "imported",
            page_type=kind.page_type,
            page_label=PAGE_LABELS.get(kind.page_type, kind.page_type),
            league_id=kind.league_id,
            saved_at=page.saved_at.isoformat() + "Z" if page.saved_at else None,
        )
        if page.saved_at is None:
            result.warnings.append("Couldn't tell when this page was saved; treating it as saved now.")
            page.saved_at = _now()

        try:
            _store(db, kind, page.html, page.saved_at, result)
        except P.ParseError as e:
            db.rollback()
            result.status = "error"
            result.summary = f"Couldn't read this {result.page_label.lower()}: {e}. Yahoo may have changed the page layout."
            return _record(db, sha, filename, source, page, kind, result)

        if result.warnings and result.status == "imported":
            result.status = "partial"
        stored = _keep_copy(data, sha, filename)
        _ensure_active_league(db, kind.league_id)
        db.commit()
        return _record(db, sha, filename, source, page, kind, result, stored)


def _record(db: Session, sha, filename, source, page, kind: PageKind | None, result: ImportResult, stored: Path | None = None) -> ImportResult:
    db.add(
        ImportRecord(
            sha256=sha,
            filename=filename,
            source=source,
            page_type=kind.page_type if kind else None,
            league_id=kind.league_id if kind else None,
            team_id=kind.team_id if kind else None,
            url=page.url if page else None,
            saved_at=page.saved_at if page else None,
            imported_at=_now(),
            status=result.status,
            message=" ".join(filter(None, [result.summary, *result.warnings])) or None,
            stored_path=str(stored) if stored else None,
        )
    )
    db.commit()
    return result


def _keep_copy(data: bytes, sha: str, filename: str) -> Path:
    config.ensure_dirs()
    ext = Path(filename).suffix.lower() or ".html"
    dest = config.IMPORTS_DIR / f"{sha[:16]}{ext}"
    if not dest.exists():
        dest.write_bytes(data)
    return dest


def _ensure_active_league(db: Session, league_id: int) -> None:
    if db.get(AppSetting, "active_league_id") is None:
        db.add(AppSetting(key="active_league_id", value=str(league_id)))


# ------------------------------------------------------------------ storing

def _store(db: Session, kind: PageKind, html: str, saved_at: datetime, result: ImportResult) -> None:
    league = db.get(League, kind.league_id) or League(id=kind.league_id)
    db.add(league)
    soup = P.soup_of(html)
    name = P.league_name(soup)
    if name:
        league.name = name
    me = P.my_team_id(soup, kind.league_id)
    if me is not None:
        league.my_team_id = me
    result.league_name = league.name

    handler = {
        "settings": _store_settings,
        "league_home": _store_league_home,
        "standings": _store_league_home,
        "team": _store_team,
        "matchup": _store_matchup,
        "players": _store_players,
    }[kind.page_type]
    handler(db, league, kind, html, saved_at, result)


def _store_settings(db, league: League, kind, html, saved_at, result) -> None:
    s = P.parse_settings(html)
    if not _newer(saved_at, league.settings_as_of):
        result.warnings.append("Older than the settings already imported; kept the newer ones.")
        return
    league.settings_json = json.dumps(
        {
            "scoring": s.scoring,
            "roster_positions": s.roster_positions,
            "max_adds_per_week": s.max_adds_per_week,
            "playoff_weeks": s.playoff_weeks,
            "trade_end_date": s.trade_end_date,
            "raw": s.raw,
        }
    )
    league.settings_as_of = saved_at
    if s.league_name:
        league.name = s.league_name
        result.league_name = s.league_name
    scoring = ", ".join(f"{k} {v:g}" for k, v in s.scoring.items())
    result.summary = f"Scoring: {scoring}. {len(s.roster_positions)} roster spots, {s.max_adds_per_week} adds per week."


def _store_league_home(db, league: League, kind, html, saved_at, result) -> None:
    page = P.parse_league_home(html, league.id)
    if _newer(saved_at, league.standings_as_of):
        for r in page.standings:
            t = db.get(FantasyTeam, (league.id, r.team_id)) or FantasyTeam(league_id=league.id, team_id=r.team_id)
            t.name, t.rank, t.wins, t.losses, t.ties = r.name, r.rank, r.wins, r.losses, r.ties
            t.points_for, t.waiver_priority, t.moves, t.as_of = r.points_for, r.waiver_priority, r.moves, saved_at
            db.add(t)
        league.standings_as_of = saved_at
    old_standings = not _newer(saved_at, league.standings_as_of) and league.standings_as_of is not None
    new_tx = 0
    for tx in page.transactions:
        exists = db.scalar(
            select(Transaction).where(
                Transaction.league_id == league.id,
                Transaction.team_name == tx.team_name,
                Transaction.when_text == tx.when_text,
                Transaction.description == tx.description,
            )
        )
        if not exists:
            db.add(Transaction(league_id=league.id, team_name=tx.team_name, when_text=tx.when_text, description=tx.description, as_of=saved_at))
            new_tx += 1
    # This week's matchups (all teams): pairings and live scores
    for mu in page.matchups:
        for me, opp, s, o in ((mu.team1, mu.team2, mu.score1, mu.score2), (mu.team2, mu.team1, mu.score2, mu.score1)):
            m = db.get(Matchup, (league.id, mu.week, me))
            if m is not None and not _newer(saved_at, m.as_of):
                continue
            if m is None:
                # Dates: take them from any matchup of the same week (Matchup pages have them)
                same_week = db.scalar(select(Matchup).where(Matchup.league_id == league.id, Matchup.week == mu.week,
                                                            Matchup.start_date.is_not(None)).limit(1))
                m = Matchup(league_id=league.id, week=mu.week, team_id=me,
                            start_date=same_week.start_date if same_week else None, end_date=same_week.end_date if same_week else None)
            m.opp_team_id, m.score, m.opp_score, m.as_of = opp, s, o, saved_at
            db.add(m)
    # Schedule tab: one team's whole season (stored for both sides of each matchup)
    sched_note = ""
    if page.schedule:
        for week, opp in page.schedule.weeks.items():
            for me, other in ((page.schedule.team_id, opp), (opp, page.schedule.team_id)):
                row = db.get(ScheduleWeek, (league.id, week, me))
                if row is None:
                    db.add(ScheduleWeek(league_id=league.id, week=week, team_id=me, opp_team_id=other, as_of=saved_at))
                elif _newer(saved_at, row.as_of):
                    row.opp_team_id, row.as_of = other, saved_at
        name = _team_name(db, league.id, page.schedule.team_id, None)
        sched_note = f" Schedule of {name}: {len(page.schedule.weeks)} weeks."
    db.flush()
    # Older standings than stored isn't a problem (e.g. several pages saved a minute apart): just say so.
    standings = "newer standings already imported" if old_standings else f"standings for {len(page.standings)} teams"
    result.summary = (sched_note.strip() + " " if sched_note else "") + f"Also: {standings}, {new_tx} new transactions" + (
        f", this week's {len(page.matchups)} matchups." if page.matchups else ".")


def _upsert_player(db: Session, ref: P.PlayerRef, saved_at: datetime, full_name: bool = True) -> None:
    p = db.get(Player, ref.id)
    if p is None:
        db.add(Player(id=ref.id, name=ref.name, nba_team=ref.nba_team, positions=ref.positions, status=ref.status, as_of=saved_at))
        return
    if not _newer(saved_at, p.as_of):
        return
    if full_name:  # matchup pages abbreviate names ("J. McCain"), so don't overwrite with those
        p.name = ref.name
        p.status = ref.status
    p.nba_team = ref.nba_team or p.nba_team
    p.positions = ref.positions or p.positions
    p.as_of = saved_at


def _set_owner(db: Session, league_id: int, player_id: int, kind: str, team_id: int | None, waiver_until: str | None, saved_at: datetime) -> None:
    o = db.get(Ownership, (league_id, player_id))
    if o is None:
        db.add(Ownership(league_id=league_id, player_id=player_id, kind=kind, team_id=team_id, waiver_until=waiver_until, as_of=saved_at))
    elif _newer(saved_at, o.as_of):
        o.kind, o.team_id, o.waiver_until, o.as_of = kind, team_id, waiver_until, saved_at


def _replace_roster(db: Session, league_id: int, team_id: int, roster: list[P.RosterEntry], saved_at: datetime, full_names: bool) -> bool:
    """Store a team's full roster if it's newer than the stored one. Returns False if skipped."""
    current = db.scalars(select(RosterSlot).where(RosterSlot.league_id == league_id, RosterSlot.team_id == team_id)).all()
    stored_as_of = max((r.as_of for r in current if r.as_of), default=None)
    if not _newer(saved_at, stored_as_of):
        return False
    new_ids = {e.player.id for e in roster}
    # Players who left this roster: forget their ownership unless something newer says otherwise.
    for r in current:
        if r.player_id not in new_ids:
            o = db.get(Ownership, (league_id, r.player_id))
            if o is not None and o.kind == "team" and o.team_id == team_id and _newer(saved_at, o.as_of):
                db.delete(o)
    db.execute(delete(RosterSlot).where(RosterSlot.league_id == league_id, RosterSlot.team_id == team_id))
    for e in roster:
        _upsert_player(db, e.player, saved_at, full_name=full_names)
        db.add(RosterSlot(league_id=league_id, team_id=team_id, player_id=e.player.id, slot=e.slot, as_of=saved_at))
        _set_owner(db, league_id, e.player.id, "team", team_id, None, saved_at)
    db.flush()
    return True


def _team_name(db: Session, league_id: int, team_id: int, name: str | None) -> str:
    t = db.get(FantasyTeam, (league_id, team_id))
    if t is None:
        t = FantasyTeam(league_id=league_id, team_id=team_id, name=name)
        db.add(t)
    elif name and not t.name:
        t.name = name
    return t.name or name or f"Team {team_id}"


def _store_team(db, league: League, kind, html, saved_at, result) -> None:
    page = P.parse_team(html, kind.team_id)
    name = _team_name(db, league.id, page.team_id, page.team_name)
    if _replace_roster(db, league.id, page.team_id, page.roster, saved_at, full_names=True):
        injured = [e.player.name for e in page.roster if e.player.status]
        result.summary = f"{name}: {len(page.roster)} players." + (f" Injury tags: {', '.join(injured)}." if injured else "")
    else:
        result.warnings.append(f"{name}'s roster is older than the one already imported; kept the newer one.")


def _store_matchup(db, league: League, kind, html, saved_at, result) -> None:
    page = P.parse_matchup(html, league.id)
    if page.week is None:
        raise P.ParseError("Couldn't find the week number")
    sides = [(page.left, page.right), (page.right, page.left)]
    stored_any = False
    for me, opp in sides:
        _team_name(db, league.id, me.team_id, me.team_name)
        m = db.get(Matchup, (league.id, page.week, me.team_id))
        if m is None or _newer(saved_at, m.as_of):
            m = m or Matchup(league_id=league.id, week=page.week, team_id=me.team_id)
            m.opp_team_id, m.score, m.opp_score = opp.team_id, me.score, opp.score
            m.start_date, m.end_date, m.as_of = page.start_date, page.end_date, saved_at
            db.add(m)
            stored_any = True
        if me.roster and not _replace_roster(db, league.id, me.team_id, me.roster, saved_at, full_names=False):
            result.warnings.append(f"{me.team_name}'s roster here is older than one already imported; kept the newer one.")
    if not stored_any:
        result.warnings.append(f"Week {page.week} score is older than the one already imported; kept the newer one.")
    result.summary = (
        f"Week {page.week} ({page.start_date} to {page.end_date}): "
        f"{page.left.team_name} {page.left.score} vs {page.right.team_name} {page.right.score}."
    )


def _store_players(db, league: League, kind, html, saved_at, result) -> None:
    page = P.parse_players(html, league.id, kind.params, saved_at)
    if not page.rows:
        raise P.ParseError("No players found in the list")
    window = page.window or "UNKNOWN"
    skipped = 0
    for r in page.rows:
        _upsert_player(db, r.player, saved_at)
        _set_owner(db, league.id, r.player.id, r.owner_kind, r.owner_team_id, r.waiver_until, saved_at)
        st = db.get(PlayerStats, (league.id, r.player.id, window))
        if st is not None and not _newer(saved_at, st.as_of):
            skipped += 1
            continue
        st = st or PlayerStats(league_id=league.id, player_id=r.player.id, window=window)
        for f in ("gp", "fpts", "mpg", "tpm", "pts", "reb", "ast", "stl", "blk", "tov", "pct_rostered", "rank_preseason", "rank_current"):
            setattr(st, f, getattr(r, f))
        st.as_of = saved_at
        db.add(st)
    counts = {k: sum(1 for r in page.rows if r.owner_kind == k) for k in ("team", "FA", "W")}
    parts = [f"{counts['team']} rostered" if counts["team"] else "", f"{counts['FA']} free agents" if counts["FA"] else "", f"{counts['W']} on waivers" if counts["W"] else ""]
    result.summary = f"{len(page.rows)} players ({', '.join(p for p in parts if p)}), stats: {window}."
    if skipped:
        result.warnings.append(f"{skipped} players already had newer stats; kept those.")


# ------------------------------------------------------------------ re-read saved pages

def reprocess_all() -> dict:
    """Read every page already imported again (oldest first), e.g. after the app learned to read more from them.
    The freshness rule still applies, so the newest data wins as before."""
    with _lock, SessionLocal() as db:
        records = db.scalars(select(ImportRecord).where(ImportRecord.status.in_(("imported", "partial")),
                                                        ImportRecord.stored_path.is_not(None))
                             .order_by(ImportRecord.saved_at)).all()
        done = errors = 0
        seen: set[str] = set()
        for rec in records:
            if rec.sha256 in seen:
                continue
            seen.add(rec.sha256)
            path = Path(rec.stored_path)
            if not path.is_file():
                continue
            try:
                page = read_page(path.read_bytes(), rec.filename, rec.saved_at)
                kind = detect(page.url)
                if kind is None:
                    continue
                _store(db, kind, page.html, page.saved_at or rec.saved_at or _now(), ImportResult(rec.filename, "imported"))
                db.commit()
                done += 1
            except (P.ParseError, NotAWebPage):
                db.rollback()
                errors += 1
        return {"pages": done, "errors": errors}


# ------------------------------------------------------------------ file helper

def import_path(path: Path, source: str = "folder") -> ImportResult:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(tzinfo=None)
    return import_bytes(path.read_bytes(), path.name, source=source, fallback_saved_at=mtime)
