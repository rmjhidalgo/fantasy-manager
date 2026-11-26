"""App settings: where data lives.

All league data stays on this PC. By default it goes in `<project>/data/`
(ignored by git). Set FM_DATA_DIR to use another folder: the friends' package does,
so their data lives in their user profile and survives installing a new version.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("FM_DATA_DIR", PROJECT_ROOT / "data"))
IMPORTS_DIR = DATA_DIR / "imports"  # private copies of imported Yahoo pages
BACKUPS_DIR = DATA_DIR / "backups"  # daily copies of the database
DB_PATH = DATA_DIR / "fantasy_manager.db"

# The built web interface (frontend/dist). When present, the backend serves it, so one
# program on one address (http://localhost:8000) is the whole app: no Node.js needed.
FRONTEND_DIST = Path(os.environ.get("FM_FRONTEND_DIR", PROJECT_ROOT / "frontend" / "dist"))

# Where "Update available" checks the newest version number (the public GitHub repo)
REPO = "rmjhidalgo/fantasy-manager"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/main/VERSION"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/latest"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def default_pages_folder() -> Path:
    """Suggested folder for saved Yahoo pages: Documents\\Fantasy Manager pages."""
    home = Path.home()
    docs = home / "Documents"
    return (docs if docs.is_dir() else home) / "Fantasy Manager pages"
