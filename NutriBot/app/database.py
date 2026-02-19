"""
Database initialization and session management.
Auto-creates SQLite DB and vault folder on first run.
"""
import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

# Paths relative to project root
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VAULT_DIR = BASE_DIR / "vault"
INBOX_DIR = VAULT_DIR / "_inbox"
BACKUPS_DIR = BASE_DIR / "backups"
DB_PATH = DATA_DIR / "db.sqlite"


def ensure_dirs():
    """Create data, vault, inbox, and backups directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def get_engine():
    """Create SQLite engine. DB file created on first connection."""
    ensure_dirs()
    return create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
        echo=False,
    )


def init_db(engine=None):
    """Create all tables. Call on app startup. Imports models to register tables."""
    import logging
    from app import models  # noqa: F401 - register models with SQLModel
    if engine is None:
        engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _migrate(engine)
    # Ensure FTS5 search table exists (no-op if FTS5 unavailable)
    try:
        from app.search_index import ensure_search_table
        ensure_search_table(engine)
    except Exception as e:
        logging.getLogger(__name__).warning("Search index init skipped: %s", e)


def _migrate(engine):
    """Add new columns to existing tables. create_all handles new tables."""
    from sqlalchemy import text
    with engine.connect() as conn:
        # Get existing columns for task_instance
        r = conn.execute(text("PRAGMA table_info(task_instance)"))
        cols = {row[1] for row in r}
        if "month" not in cols:
            conn.execute(text("ALTER TABLE task_instance ADD COLUMN month INTEGER"))
            conn.commit()
        if "created_from_generation" not in cols:
            conn.execute(text("ALTER TABLE task_instance ADD COLUMN created_from_generation INTEGER DEFAULT 0"))
            conn.commit()
        if "completion_date" not in cols:
            conn.execute(text("ALTER TABLE task_instance ADD COLUMN completion_date DATE"))
            conn.commit()
        # evidence_item: multi-tag support
        r = conn.execute(text("PRAGMA table_info(evidence_item)"))
        ev_cols = {row[1] for row in r}
        if "evidence_types_json" not in ev_cols:
            conn.execute(text("ALTER TABLE evidence_item ADD COLUMN evidence_types_json TEXT DEFAULT ''"))
            conn.commit()


def get_session():
    """Yield a database session for FastAPI Depends."""
    engine = get_engine()
    init_db(engine)
    with Session(engine) as session:
        yield session
