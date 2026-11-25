"""Database setup (SQLite via SQLAlchemy). Tables are added in later milestones."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config


class Base(DeclarativeBase):
    pass


engine = create_engine(f"sqlite:///{config.DB_PATH}")
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    config.ensure_dirs()
    Base.metadata.create_all(engine)


def db_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
