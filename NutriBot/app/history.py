"""
Historical execution records: per-year task summaries for audit history.
Phase 6: HIST-01, HIST-02 — per-year execution records, comparison view.
"""
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app.models import ChecklistItem, EvidenceItem, NoteLog, TaskInstance, TaskTemplate
from app.trends import find_baseline_task


def _task_record(db: Session, t: TaskInstance) -> dict[str, Any]:
    """Build execution record for a single task."""
    t.template = t.template or db.get(TaskTemplate, t.template_id)
    checklist = list(db.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == t.id).order_by(ChecklistItem.sort_order)
    ).all())
    notes = list(db.exec(
        select(NoteLog).where(NoteLog.task_id == t.id).order_by(NoteLog.created_at.desc())
    ).all())
    evidence_count = len(list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == t.id)).all()))

    completion_date = t.completion_date
    if not completion_date and t.status == "completed" and t.updated_at:
        completion_date = t.updated_at.date() if hasattr(t.updated_at, "date") else None

    checklist_done = sum(1 for c in checklist if c.completed)
    checklist_pct = round(checklist_done / len(checklist) * 100, 0) if checklist else 0

    notes_preview = (notes[0].content[:80] + "…") if notes and len(notes[0].content) > 80 else (notes[0].content if notes else "")

    title = f"{t.template.name if t.template else 'Task'}"
    title += f" - {t.year}-{t.month:02d}" if t.month else f" ({t.year})"

    return {
        "task_id": t.id,
        "title": title,
        "category": t.template.category if t.template else "Other",
        "due_date": t.due_date,
        "status": t.status,
        "completion_date": completion_date,
        "notes_preview": notes_preview,
        "checklist_pct": checklist_pct,
        "evidence_count": evidence_count,
    }


def build_execution_records(db: Session, year: int) -> list[dict[str, Any]]:
    """Build execution summary per task for a year. Group by category."""
    tasks = list(db.exec(select(TaskInstance).where(TaskInstance.year == year)).all())
    records = []
    for t in tasks:
        t.template = db.get(TaskTemplate, t.template_id)
        checklist = list(db.exec(
            select(ChecklistItem).where(ChecklistItem.task_id == t.id).order_by(ChecklistItem.sort_order)
        ).all())
        notes = list(db.exec(
            select(NoteLog).where(NoteLog.task_id == t.id).order_by(NoteLog.created_at.desc())
        ).all())
        evidence_count = len(list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == t.id)).all()))

        completion_date = t.completion_date
        if not completion_date and t.status == "completed" and t.updated_at:
            completion_date = t.updated_at.date() if hasattr(t.updated_at, "date") else None

        checklist_done = sum(1 for c in checklist if c.completed)
        checklist_pct = round(checklist_done / len(checklist) * 100, 0) if checklist else 0

        notes_preview = ""
        if notes:
            notes_preview = (notes[0].content[:80] + "…") if len(notes[0].content) > 80 else notes[0].content

        title = f"{t.template.name if t.template else 'Task'}"
        if t.month:
            title += f" - {t.year}-{t.month:02d}"
        else:
            title += f" ({t.year})"

        records.append({
            "task_id": t.id,
            "title": title,
            "category": t.template.category if t.template else "Other",
            "due_date": t.due_date,
            "status": t.status,
            "completion_date": completion_date,
            "notes_preview": notes_preview,
            "notes_full": t.notes or "",
            "checklist_pct": checklist_pct,
            "evidence_count": evidence_count,
        })
    return sorted(records, key=lambda r: (r["category"], r["due_date"] or date(year, 12, 31)))


def build_comparison_pairs(
    db: Session, year: int, baseline: int
) -> list[dict[str, Any]]:
    """Build task-by-task comparison: current year vs baseline. Only pairs where both exist."""
    tasks_year = list(db.exec(select(TaskInstance).where(TaskInstance.year == year)).all())
    pairs = []
    for t in tasks_year:
        t.template = db.get(TaskTemplate, t.template_id)
        base = find_baseline_task(db, t, baseline)
        if not base:
            continue
        base.template = db.get(TaskTemplate, base.template_id)
        pairs.append({
            "current_task": t,
            "baseline_task": base,
            "current_record": _task_record(db, t),
            "baseline_record": _task_record(db, base),
        })
    return sorted(pairs, key=lambda p: (p["current_record"]["category"], p["current_record"]["due_date"] or date(year, 12, 31)))
