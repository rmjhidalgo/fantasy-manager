"""Database setup (SQLite via SQLAlchemy)."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config


class Base(DeclarativeBase):
    pass


# check_same_thread=False: the folder watcher imports from a background thread.
engine = create_engine(
    f"sqlite:///{config.DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    config.ensure_dirs()
    from app.db import models  # noqa: F401  (registers tables)

    Base.metadata.create_all(engine)


def db_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
