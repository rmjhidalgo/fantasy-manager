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


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("league_id", "team_name", "when_text", "description"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer)
    team_name: Mapped[str | None] = mapped_column(String)
    when_text: Mapped[str | None] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    as_of: Mapped[datetime | None] = mapped_column(DateTime)
