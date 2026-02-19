"""
Settings and regulations library storage (JSON under data/).
No schema changes; all metadata in JSON files.
"""
import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from app.database import DATA_DIR, VAULT_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"
REG_LIBRARY_PATH = DATA_DIR / "reg_library.json"
REGULATIONS_DIR = VAULT_DIR / "_regulations"
REG_TRASH_DIR = VAULT_DIR / "_regulations" / "_trash"

DEFAULT_SETTINGS = {
    "onboarding_complete": False,
    "district_name": "",
    "state": "Idaho",
    "timezone": "America/Boise",
    "current_school_year": "",
    "programs": {
        "NSLP": False,
        "SBP": False,
        "SMP": False,
        "Summer": False,
        "CACFP": False,
        "FFVP": False,
    },
    "monthly_claim_internal_deadline_day": 15,
    "month_end_close_day": 28,
    "verification_window_start": "10-01",
    "verification_complete_deadline": "11-15",
    "default_retention_policy": "",
    "default_minimal_audit_set": "",
    "enable_monthly_claims_tracking": True,
}


def load_settings() -> dict[str, Any]:
    """Load settings from data/settings.json."""
    if not SETTINGS_PATH.exists():
        return dict(DEFAULT_SETTINGS)
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for k, v in DEFAULT_SETTINGS.items():
        if k not in data:
            data[k] = v
    if not isinstance(data.get("programs"), dict):
        data["programs"] = dict(DEFAULT_SETTINGS["programs"])
    return data


def save_settings(data: dict[str, Any]) -> None:
    """Save settings to data/settings.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def is_onboarding_complete() -> bool:
    """Check if onboarding has been completed."""
    s = load_settings()
    return bool(s.get("onboarding_complete", False))


def load_reg_library() -> list[dict[str, Any]]:
    """Load regulations from data/reg_library.json."""
    if not REG_LIBRARY_PATH.exists():
        return []
    with open(REG_LIBRARY_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_reg_library(regs: list[dict[str, Any]]) -> None:
    """Save regulations to data/reg_library.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(REG_LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump(regs, f, indent=2)


def add_reg(reg: dict[str, Any]) -> None:
    """Add a regulation. Assigns id if missing."""
    regs = load_reg_library()
    if "id" not in reg or not reg["id"]:
        reg["id"] = str(uuid.uuid4())
    regs.append(reg)
    save_reg_library(regs)


def get_reg(reg_id: str) -> Optional[dict[str, Any]]:
    """Get regulation by id."""
    for r in load_reg_library():
        if r.get("id") == reg_id:
            return r
    return None


def update_reg(reg_id: str, updates: dict[str, Any]) -> bool:
    """Update regulation by id. Returns True if found."""
    regs = load_reg_library()
    for i, r in enumerate(regs):
        if r.get("id") == reg_id:
            regs[i] = {**r, **updates}
            save_reg_library(regs)
            return True
    return False


def delete_reg(reg_id: str) -> bool:
    """Remove regulation by id. Returns True if found."""
    regs = load_reg_library()
    for i, r in enumerate(regs):
        if r.get("id") == reg_id:
            regs.pop(i)
            save_reg_library(regs)
            return True
    return False


def compute_next_review_due(last_reviewed: Optional[str], frequency_days: int = 365) -> Optional[str]:
    """Compute next_review_due from last_reviewed (YYYY-MM-DD) and frequency_days."""
    if not last_reviewed:
        return None
    try:
        dt = datetime.strptime(last_reviewed, "%Y-%m-%d").date()
        next_dt = dt + timedelta(days=frequency_days)
        return next_dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def regs_due_soon_count(within_days: int = 30) -> int:
    """Count regulations with next_review_due within N days."""
    today = date.today()
    cutoff = today + timedelta(days=within_days)
    count = 0
    for r in load_reg_library():
        due = r.get("next_review_due")
        if not due:
            continue
        try:
            d = datetime.strptime(due, "%Y-%m-%d").date()
            if today <= d <= cutoff:
                count += 1
        except (ValueError, TypeError):
            pass
    return count


def ensure_regulations_dirs() -> None:
    """Create vault/_regulations and _trash if needed."""
    REGULATIONS_DIR.mkdir(parents=True, exist_ok=True)
    REG_TRASH_DIR.mkdir(parents=True, exist_ok=True)
