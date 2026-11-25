"""App settings: where data lives.

All league data stays on this PC. By default it goes in `<project>/data/`
(ignored by git). Set FM_DATA_DIR to use another folder.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("FM_DATA_DIR", PROJECT_ROOT / "data"))
IMPORTS_DIR = DATA_DIR / "imports"  # private copies of imported Yahoo pages
DB_PATH = DATA_DIR / "fantasy_manager.db"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
