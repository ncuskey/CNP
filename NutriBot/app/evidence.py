"""
Evidence vault: storage, retention rules, missing evidence logic.
"""
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.database import INBOX_DIR, VAULT_DIR
from app.models import (
    EvidenceItem,
    EvidenceRequirement,
    RetentionRule,
    TaskInstance,
    TaskTemplate,
)


def get_evidence_types(item: EvidenceItem) -> list[str]:
    """Return all evidence types for an item. One document can satisfy multiple requirements."""
    if item.evidence_types_json:
        try:
            types = json.loads(item.evidence_types_json)
            if isinstance(types, list) and types:
                return types
        except (json.JSONDecodeError, TypeError):
            pass
    return [item.evidence_type] if item.evidence_type else []


def get_task_display_name(task: TaskInstance, template: Optional[TaskTemplate]) -> str:
    """Safe task name for folder paths."""
    base = (template.name if template else "Task").replace("/", "-").replace("\\", "-")[:50]
    if task.month:
        return f"{base}-{task.year}-{task.month:02d}"
    return f"{base}-{task.year}"


def get_vault_path(task: TaskInstance, template: Optional[TaskTemplate]) -> Path:
    """vault/YYYY/Category/TaskName/"""
    year = task.year
    cat = (template.category if template else "Other").replace("/", "-").replace("\\", "-")
    name = get_task_display_name(task, template)
    return VAULT_DIR / str(year) / cat / name


def store_evidence_file(
    task: TaskInstance,
    template: Optional[TaskTemplate],
    uploaded_path: Path,
    original_filename: str,
) -> tuple[Path, str, str]:
    """
    Copy file into vault. Returns (full_path, stored_filename, rel_path for DB).
    Adds suffix if collision.
    """
    vault_sub = get_vault_path(task, template)
    vault_sub.mkdir(parents=True, exist_ok=True)
    stem = Path(original_filename).stem
    ext = Path(original_filename).suffix
    stored = f"{stem}{ext}"
    dest = vault_sub / stored
    counter = 1
    while dest.exists():
        stored = f"{stem}_{counter}{ext}"
        dest = vault_sub / stored
        counter += 1
    shutil.copy2(uploaded_path, dest)
    rel_path = str(dest.relative_to(VAULT_DIR)).replace("\\", "/")
    return dest, stored, rel_path


def store_evidence_from_inbox(
    task: TaskInstance,
    template: Optional[TaskTemplate],
    inbox_filename: str,
) -> tuple[Path, str, str]:
    """
    Move file from vault/_inbox/ to task vault folder.
    Returns (full_path, stored_filename, rel_path for DB).
    """
    src = INBOX_DIR / inbox_filename
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Inbox file not found: {inbox_filename}")
    vault_sub = get_vault_path(task, template)
    vault_sub.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    ext = src.suffix
    stored = f"{stem}{ext}"
    dest = vault_sub / stored
    counter = 1
    while dest.exists():
        stored = f"{stem}_{counter}{ext}"
        dest = vault_sub / stored
        counter += 1
    shutil.move(str(src), str(dest))
    rel_path = str(dest.relative_to(VAULT_DIR)).replace("\\", "/")
    return dest, stored, rel_path


def list_inbox_files() -> list[Path]:
    """Return list of files in vault/_inbox/ (not yet assigned)."""
    if not INBOX_DIR.exists():
        return []
    return [p for p in INBOX_DIR.iterdir() if p.is_file()]


def delete_inbox_file(filename: str) -> bool:
    """Delete file from inbox. Returns True if deleted."""
    p = INBOX_DIR / filename
    if p.exists() and p.is_file():
        p.unlink()
        return True
    return False


def apply_retention_rule(
    db: Session,
    category: str,
    evidence_type: str,
    importance: str,
    added_at: datetime,
) -> tuple[Optional[date], Optional[date], Optional[int], str]:
    """
    Find best matching RetentionRule and return (keep_until, review_date, rule_id, description).
    Match: category (required), then evidence_type (or blank), then importance (or blank).
    """
    rules = list(db.exec(select(RetentionRule).where(RetentionRule.category == category)).all())
    best = None
    best_score = -1
    for r in rules:
        score = 0
        if r.evidence_type and r.evidence_type == evidence_type:
            score += 2
        elif not r.evidence_type:
            score += 1
        if r.importance and r.importance == importance:
            score += 2
        elif not r.importance:
            score += 1
        if score > best_score:
            best_score = score
            best = r
    if not best:
        return None, None, None, ""
    if best.is_permanent:
        return None, None, best.id, best.description
    if best.years_to_keep:
        keep_until = added_at.date() + timedelta(days=365 * best.years_to_keep)
        review_date = keep_until - timedelta(days=60)
        return keep_until, review_date, best.id, best.description
    return None, None, best.id, best.description


def move_to_trash(file_path: str) -> Optional[Path]:
    """Move evidence file to vault/_trash/YYYY-MM-DD/. Returns new path or None."""
    full = VAULT_DIR / file_path
    if not full.exists():
        return None
    trash_dir = VAULT_DIR / "_trash" / datetime.now().strftime("%Y-%m-%d")
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / full.name
    counter = 1
    while dest.exists():
        dest = trash_dir / f"{full.stem}_{counter}{full.suffix}"
        counter += 1
    shutil.move(str(full), str(dest))
    return dest


def compute_missing_evidence(
    db: Session,
    task: TaskInstance,
    template: Optional[TaskTemplate],
) -> tuple[int, int]:
    """
    Returns (missing_required, missing_supporting).
    required: needs EvidenceItem with importance==required
    supporting: can be satisfied by supporting or required
    """
    if not template:
        return 0, 0
    reqs = list(db.exec(
        select(EvidenceRequirement).where(EvidenceRequirement.template_id == template.id)
    ).all())
    items = list(db.exec(
        select(EvidenceItem).where(EvidenceItem.task_id == task.id)
    ).all())
    type_importance = set()
    for e in items:
        for et in get_evidence_types(e):
            type_importance.add((et, e.importance))
    missing_req = 0
    missing_sup = 0
    for r in reqs:
        satisfied = False
        if r.importance == "required":
            satisfied = (r.evidence_type, "required") in type_importance
            if not satisfied:
                missing_req += 1
        elif r.importance == "supporting":
            satisfied = (
                (r.evidence_type, "supporting") in type_importance or
                (r.evidence_type, "required") in type_importance
            )
            if not satisfied:
                missing_sup += 1
        # nice_to_have is informational only
    return missing_req, missing_sup


EXCLUDED_VAULT_DIRS = {"_inbox", "_trash", "_audit_packets", "_untracked"}


def get_orphaned_evidence(db: Session, year: Optional[int] = None) -> list[EvidenceItem]:
    """EvidenceItem records where VAULT_DIR/file_path does not exist."""
    items = list(db.exec(select(EvidenceItem)).all())
    orphaned = []
    for e in items:
        if not e.file_path:
            continue
        full = VAULT_DIR / e.file_path
        if not full.exists() or not full.is_file():
            if year is not None:
                task = db.get(TaskInstance, e.task_id)
                if task and task.year != year:
                    continue
            orphaned.append(e)
    return orphaned


def get_orphaned_files(db: Session, year: Optional[int] = None) -> list[Path]:
    """Files in vault not in any EvidenceItem.file_path. Excludes _inbox, _trash, _audit_packets, _untracked."""
    tracked = {e.file_path.replace("\\", "/") for e in db.exec(select(EvidenceItem)).all() if e.file_path}
    orphaned: list[Path] = []
    if not VAULT_DIR.exists():
        return []
    for p in VAULT_DIR.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(VAULT_DIR)).replace("\\", "/")
        if rel in tracked:
            continue
        parts = rel.split("/")
        if parts and parts[0] in EXCLUDED_VAULT_DIRS:
            continue
        if year is not None and len(parts) >= 1:
            try:
                y = int(parts[0])
                if y != year:
                    continue
            except ValueError:
                pass
        orphaned.append(p)
    return orphaned


def move_orphaned_to_untracked(paths: list[str]) -> int:
    """Move orphaned files to vault/_untracked/{year}/ or _untracked/unknown/. Returns count moved."""
    untracked_base = VAULT_DIR / "_untracked"
    untracked_base.mkdir(parents=True, exist_ok=True)
    moved = 0
    for rel in paths:
        full = VAULT_DIR / rel
        if not full.exists() or not full.is_file():
            continue
        parts = rel.replace("\\", "/").split("/")
        year_dir = "unknown"
        if len(parts) >= 1:
            try:
                y = int(parts[0])
                year_dir = str(y)
            except ValueError:
                pass
        dest_dir = untracked_base / year_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / full.name
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{full.stem}_{counter}{full.suffix}"
            counter += 1
        shutil.move(str(full), str(dest))
        moved += 1
    return moved


def seed_retention_rules(db: Session) -> int:
    """Seed default retention rules if table empty. Returns count added."""
    existing = db.exec(select(RetentionRule)).first()
    if existing:
        return 0
    defaults = [
        RetentionRule(category="Verification", years_to_keep=3, description="Verification records - 3 years"),
        RetentionRule(category="Claims", years_to_keep=3, description="Claim records - 3 years"),
        RetentionRule(category="Procurement", years_to_keep=3, description="Procurement docs - 3 years"),
        RetentionRule(category="Training", years_to_keep=3, description="Training records - 3 years"),
        RetentionRule(category="CEP", years_to_keep=3, description="CEP documentation - 3 years"),
        RetentionRule(category="Reviews", years_to_keep=3, description="Review records - 3 years"),
        RetentionRule(category="Policies", is_permanent=True, description="Policies - permanent"),
    ]
    for r in defaults:
        db.add(r)
    db.commit()
    return len(defaults)
