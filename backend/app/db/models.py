"""Database tables for imported Yahoo data.

Freshness rule: every group of facts remembers when the page it came from was
saved (`as_of`, UTC). A page saved earlier than what's stored never overwrites it.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)


class ImportRecord(Base):
    __tablename__ = "imports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(String, index=True)
    filename: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)  # "upload" | "folder"
    page_type: Mapped[str | None] = mapped_column(String)
    league_id: Mapped[int | None] = mapped_column(Integer)
    team_id: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(Text)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime)
    imported_at: Mapped[datetime] = mapped_column(DateTime)
    # imported | partial (some parts older than stored data) | duplicate | unsupported | error
    status: Mapped[str] = mapped_column(String)
    message: Mapped[str | None] = mapped_column(Text)
    stored_path: Mapped[str | None] = mapped_column(Text)


class League(Base):
    __tablename__ = "leagues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Yahoo league ID
    name: Mapped[str | None] = mapped_column(String)
    my_team_id: Mapped[int | None] = mapped_column(Integer)
    settings_json: Mapped[str | None] = mapped_column(Text)
    settings_as_of: Mapped[datetime | None] = mapped_column(DateTime)
    standings_as_of: Mapped[datetime | None] = mapped_column(DateTime)


class FantasyTeam(Base):
    __tablename__ = "fantasy_teams"
    league_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String)
    rank: Mapped[int | None] = mapped_column(Integer)
    wins: Mapped[int | None] = mapped_column(Integer)
    losses: Mapped[int | None] = mapped_column(Integer)
    ties: Mapped[int | None] = mapped_column(Integer)
    points_for: Mapped[float | None] = mapped_column(Float)
    waiver_priority: Mapped[int | None] = mapped_column(Integer)
    moves: Mapped[int | None] = mapped_column(Integer)
    as_of: Mapped[datetime | None] = mapped_column(DateTime)


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Yahoo player ID
    name: Mapped[str] = mapped_column(String)
    nba_team: Mapped[str | None] = mapped_column(String)
    positions: Mapped[str | None] = mapped_column(String)  # "PG,SG"
    status: Mapped[str | None] = mapped_column(String)  # O, Q, GTD, INJ, ... or None when healthy
    as_of: Mapped[datetime | None] = mapped_column(DateTime)


class PlayerStats(Base):
    """Per-player stats from a players list, for one stat window (e.g. season averages)."""

    __tablename__ = "player_stats"
    league_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window: Mapped[str] = mapped_column(String, primary_key=True)  # Yahoo stat1 code, e.g. S_AS_2026
    gp: Mapped[int | None] = mapped_column(Integer)
    fpts: Mapped[float | None] = mapped_column(Float)
    mpg: Mapped[float | None] = mapped_column(Float)
    tpm: Mapped[float | None] = mapped_column(Float)
    pts: Mapped[float | None] = mapped_column(Float)
    reb: Mapped[float | None] = mapped_column(Float)
    ast: Mapped[float | None] = mapped_column(Float)
    stl: Mapped[float | None] = mapped_column(Float)
    blk: Mapped[float | None] = mapped_column(Float)
    tov: Mapped[float | None] = mapped_column(Float)
    pct_rostered: Mapped[float | None] = mapped_column(Float)
    rank_preseason: Mapped[int | None] = mapped_column(Integer)
    rank_current: Mapped[int | None] = mapped_column(Integer)
    as_of: Mapped[datetime | None] = mapped_column(DateTime)


class Ownership(Base):
    """Who holds a player in a league: a team, a free agent (FA), or on waivers (W)."""

    __tablename__ = "ownership"
    league_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String)  # "team" | "FA" | "W"
    team_id: Mapped[int | None] = mapped_column(Integer)
    waiver_until: Mapped[str | None] = mapped_column(String)  # ISO date
    as_of: Mapped[datetime | None] = mapped_column(DateTime)


class RosterSlot(Base):
    __tablename__ = "roster_slots"
    league_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slot: Mapped[str] = mapped_column(String)  # PG, SG, ..., Util, BN, IL
    as_of: Mapped[datetime | None] = mapped_column(DateTime)


class Matchup(Base):
    """One row per team per week (each matchup is stored from both sides)."""

    __tablename__ = "matchups"
    league_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opp_team_id: Mapped[int] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)
    opp_score: Mapped[float | None] = mapped_column(Float)
    start_date: Mapped[str | None] = mapped_column(String)
    end_date: Mapped[str | None] = mapped_column(String)
    as_of: Mapped[datetime | None] = mapped_column(DateTime)


class NbaGame(Base):
    __tablename__ = "nba_games"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # NBA gameId
    date_et: Mapped[str] = mapped_column(String, index=True)  # US Eastern date, YYYY-MM-DD
    start_utc: Mapped[datetime | None] = mapped_column(DateTime)
    home: Mapped[str] = mapped_column(String)  # team tricode
    away: Mapped[str] = mapped_column(String)
    status: Mapped[int] = mapped_column(Integer)  # 1 scheduled, 2 live, 3 final
    regular_season: Mapped[int] = mapped_column(Integer, default=1)


class NbaPlayer(Base):
    __tablename__ = "nba_players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # NBA personId
    name: Mapped[str] = mapped_column(String)
    team: Mapped[str | None] = mapped_column(String)
    position: Mapped[str | None] = mapped_column(String)  # NBA.com position: G, F, C, G-F, F-C, ...


class NbaInjury(Base):
    """An injured NBA player with an estimated return date (ESPN's public injury list, refreshed with NBA data)."""

    __tablename__ = "nba_injuries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nba_id: Mapped[int | None] = mapped_column(Integer, index=True)  # matched NBA player, if found
    name: Mapped[str] = mapped_column(String)
    team: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # "Out" | "Day-To-Day"
    return_date: Mapped[str | None] = mapped_column(String)  # ISO date: first day he's expected to be able to play
    injury: Mapped[str | None] = mapped_column(String)  # e.g. "Knee - Patellar tendon tear"
    comment: Mapped[str | None] = mapped_column(Text)
    reported: Mapped[str | None] = mapped_column(String)  # ISO date of the latest news


class OutlookHistory(Base):
    """Win chance over the week: one point each time new data (an import or NBA refresh) changes the outlook."""

    __tablename__ = "outlook_history"
    __table_args__ = (UniqueConstraint("league_id", "week", "team_id", "data_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer)
    week: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int] = mapped_column(Integer)
    data_key: Mapped[str] = mapped_column(String)  # matchup page time + NBA refresh time
    computed_at: Mapped[datetime] = mapped_column(DateTime)
    win_prob: Mapped[float] = mapped_column(Float)
    my_final: Mapped[float] = mapped_column(Float)
    opp_final: Mapped[float] = mapped_column(Float)


class ScheduleWeek(Base):
    """Who plays whom in each week of the season (from the League page's Schedule tab), stored for both teams."""

    __tablename__ = "schedule_weeks"
    league_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opp_team_id: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[datetime | None] = mapped_column(DateTime)


class MoveLog(Base):
    """A suggested move you opened on Yahoo; later imports show whether it happened."""

    __tablename__ = "move_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)  # UTC
    source: Mapped[str] = mapped_column(String)  # "suggested" | "free agents" | "streaming"
    horizon: Mapped[str | None] = mapped_column(String)  # A/B/C/D for suggested moves
    add_yahoo_id: Mapped[int | None] = mapped_column(Integer)
    add_nba_id: Mapped[int | None] = mapped_column(Integer)
    add_name: Mapped[str] = mapped_column(String)
    drop_yahoo_id: Mapped[int | None] = mapped_column(Integer)
    drop_name: Mapped[str | None] = mapped_column(String)
    gain: Mapped[float | None] = mapped_column(Float)
    # open | done | missed (someone else got him) | not done | dismissed
    status: Mapped[str] = mapped_column(String, default="open")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)


class GameLog(Base):
    """One finished game for one player."""

    __tablename__ = "game_logs"
    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # NBA personId
    game_id: Mapped[str] = mapped_column(String, primary_key=True)
    date_et: Mapped[str] = mapped_column(String, index=True)
    team: Mapped[str | None] = mapped_column(String)
    min: Mapped[float | None] = mapped_column(Float)
    pts: Mapped[float] = mapped_column(Float, default=0)
    reb: Mapped[float] = mapped_column(Float, default=0)
    ast: Mapped[float] = mapped_column(Float, default=0)
    stl: Mapped[float] = mapped_column(Float, default=0)
    blk: Mapped[float] = mapped_column(Float, default=0)
    tov: Mapped[float] = mapped_column(Float, default=0)
    fg3m: Mapped[float] = mapped_column(Float, default=0)
    fgm: Mapped[float] = mapped_column(Float, default=0)
    fga: Mapped[float] = mapped_column(Float, default=0)
    ftm: Mapped[float] = mapped_column(Float, default=0)
    fta: Mapped[float] = mapped_column(Float, default=0)
    oreb: Mapped[float] = mapped_column(Float, default=0)
    dreb: Mapped[float] = mapped_column(Float, default=0)
    pf: Mapped[float] = mapped_column(Float, default=0)


class PlayerMap(Base):
    """Links a Yahoo player to an NBA player. method: auto | manual | none (manually marked as no match)."""

    __tablename__ = "player_map"
    yahoo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nba_id: Mapped[int | None] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("league_id", "team_name", "when_text", "description"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer)
    team_name: Mapped[str | None] = mapped_column(String)
    when_text: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    as_of: Mapped[datetime | None] = mapped_column(DateTime)
