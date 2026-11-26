import os
import tempfile
from pathlib import Path

import pytest

# Use a throwaway data folder so tests never touch real data. Must run before `app` is imported.
os.environ["FM_DATA_DIR"] = tempfile.mkdtemp(prefix="fm_test_")
os.environ["FM_NO_BACKGROUND"] = "1"  # no NBA downloads or folder watching during tests

from app.db import Base, engine, init_db  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name_part: str) -> Path:
    """Find a saved Yahoo page in tests/fixtures by its exact name or part of its name."""
    if (FIXTURES / name_part).is_file():
        return FIXTURES / name_part
    matches = sorted(p for p in FIXTURES.glob("*") if name_part in p.name)
    if not matches:
        pytest.skip(f"fixture '{name_part}' not present (saved pages are private and not in git)")
    return matches[0]


def taken_pages() -> list[Path]:
    pages = sorted(FIXTURES.glob("Player List(Taken*"))
    if not pages:
        pytest.skip("taken-player fixtures not present")
    return pages


@pytest.fixture
def fresh_db():
    from app.importer import service

    init_db()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    del service
