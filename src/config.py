"""Application configuration and shared paths."""
from pathlib import Path

# Project root (parent of the "src" folder).
BASE_DIR = Path(__file__).resolve().parent.parent

# Directory where uploaded images/files are stored on disk.
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# SQLite database file location.
DB_PATH = BASE_DIR / "data" / "consultations.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Jinja2 templates directory.
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Static files directory (favicons, etc.)
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Max upload size guard (10 MB) — optional soft limit used in the endpoint.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
