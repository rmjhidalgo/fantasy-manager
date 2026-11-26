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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_all() makes new tables but doesn't add new columns to existing ones: add them here."""
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {row[1] for row in conn.execute(text(f'PRAGMA table_info("{table.name}")'))}
            for col in table.columns:
                if col.name not in have:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'))


def db_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
