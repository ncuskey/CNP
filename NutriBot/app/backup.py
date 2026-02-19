"""
Simple backup system: db, retention rules, templates config.
No compression. Stored in backups/YYYY-MM-DD_HHMM/
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

from app.database import BACKUPS_DIR, DATA_DIR, DB_PATH


def create_backup() -> Path:
    """
    Copy db.sqlite and optional configs to backups/YYYY-MM-DD_HHMM/.
    Returns path to backup folder.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_dir = BACKUPS_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        shutil.copy2(DB_PATH, out_dir / "db.sqlite")

    # Retention rules export (from DB - we'd need a session; skip for simplicity, db has it)
    # Templates config - if exists
    config_path = DATA_DIR / "templates_config.json"
    if config_path.exists():
        shutil.copy2(config_path, out_dir / "templates_config.json")

    return out_dir


def list_backups() -> list[tuple[Path, datetime]]:
    """Return list of (path, datetime) for backup folders, newest first."""
    if not BACKUPS_DIR.exists():
        return []
    items = []
    for p in BACKUPS_DIR.iterdir():
        if p.is_dir():
            try:
                dt = datetime.strptime(p.name, "%Y-%m-%d_%H%M")
                items.append((p, dt))
            except ValueError:
                pass
    items.sort(key=lambda x: x[1], reverse=True)
    return items


def restore_backup(backup_path: Path) -> None:
    """Restore db.sqlite from backup folder. Overwrites current DB."""
    src = backup_path / "db.sqlite"
    if not src.exists():
        raise FileNotFoundError(f"No db.sqlite in {backup_path}")
    shutil.copy2(src, DB_PATH)


def should_auto_backup() -> bool:
    """True if last backup is > 24h ago or no backups exist."""
    items = list_backups()
    if not items:
        return True
    last_dt = items[0][1]
    return (datetime.now() - last_dt).total_seconds() > 24 * 3600
