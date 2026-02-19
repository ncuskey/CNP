"""
Document generation: cover sheet, memo, evidence index.
Renders HTML, generates PDF, stores in vault/_generated/, creates EvidenceItem.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlmodel import Session, select

from app.database import VAULT_DIR
from app.evidence import get_task_display_name, get_vault_path
from app.models import (
    ChecklistItem,
    EvidenceItem,
    GeneratedDocument,
    NoteLog,
    TaskInstance,
    TaskTemplate,
)
from app.pdf_engine import render_html_to_pdf

GENERATED_SUBDIR = "_generated"


def get_generated_dir(task: TaskInstance, template: Optional[TaskTemplate]) -> Path:
    """vault/YYYY/Category/TaskName/_generated/"""
    return get_vault_path(task, template) / GENERATED_SUBDIR


def write_pdf_and_register(
    html: str,
    task: TaskInstance,
    template: Optional[TaskTemplate],
    doc_type: str,
    base_name: str,
    db: Session,
    evidence_type: str = "other",
) -> tuple[Path, str]:
    """
    Render HTML to PDF, save to vault/_generated/, create EvidenceItem.
    Returns (full_path, rel_path). Uses versioned filename if collision.
    """
    gen_dir = get_generated_dir(task, template)
    gen_dir.mkdir(parents=True, exist_ok=True)
    stem = base_name
    ext = ".pdf"
    filename = f"{stem}{ext}"
    dest = gen_dir / filename
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stem}_{ts}{ext}"
        dest = gen_dir / filename
    render_html_to_pdf(html, str(dest))
    rel_path = str(dest.relative_to(VAULT_DIR)).replace("\\", "/")

    item = EvidenceItem(
        task_id=task.id,
        category=template.category if template else "",
        evidence_type=evidence_type,
        importance="supporting",
        description=f"Generated {doc_type}",
        original_filename=filename,
        stored_filename=filename,
        file_path=rel_path,
    )
    db.add(item)
    db.commit()
    return dest, rel_path


def build_cover_sheet_context(
    db: Session,
    task: TaskInstance,
    template: Optional[TaskTemplate],
    notes_limit: int = 5,
) -> dict[str, Any]:
    """Build context for cover sheet template."""
    checklist = list(db.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == task.id).order_by(ChecklistItem.sort_order)
    ).all())
    notes = list(db.exec(
        select(NoteLog).where(NoteLog.task_id == task.id).order_by(NoteLog.created_at.desc()).limit(notes_limit)
    ).all())
    evidence = list(db.exec(
        select(EvidenceItem).where(EvidenceItem.task_id == task.id)
    ).all())
    from app.evidence import compute_missing_evidence
    missing_req, missing_sup = compute_missing_evidence(db, task, template)
    completed = sum(1 for c in checklist if c.completed)
    return {
        "task": task,
        "template": template,
        "checklist": checklist,
        "checklist_completed": completed,
        "checklist_total": len(checklist),
        "notes": notes,
        "evidence": evidence,
        "missing_required": missing_req,
        "missing_supporting": missing_sup,
        "created_at": datetime.now(),
        "display_name": get_task_display_name(task, template),
    }


def build_memo_context(
    db: Session,
    task: TaskInstance,
    template: Optional[TaskTemplate],
    content: dict[str, str],
) -> dict[str, Any]:
    """Build context for memo template. content has: context, actions_taken, decision, risks."""
    checklist = list(db.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == task.id).order_by(ChecklistItem.sort_order)
    ).all())
    notes = list(db.exec(
        select(NoteLog).where(NoteLog.task_id == task.id).order_by(NoteLog.created_at.desc()).limit(10)
    ).all())
    actions = []
    for c in checklist:
        if c.completed:
            actions.append(f"✓ {c.text}")
    for n in notes:
        actions.append(f"[{n.created_at.strftime('%Y-%m-%d')}] {n.content[:200]}")
    return {
        "task": task,
        "template": template,
        "display_name": get_task_display_name(task, template),
        "context": content.get("context", ""),
        "actions_taken": content.get("actions_taken", "\n".join(actions)),
        "decision": content.get("decision", ""),
        "risks": content.get("risks", ""),
        "date": content.get("date", datetime.now().strftime("%Y-%m-%d")),
    }


def build_evidence_index_context(
    db: Session,
    task: TaskInstance,
    template: Optional[TaskTemplate],
) -> dict[str, Any]:
    """Build context for evidence index template."""
    from app.evidence import get_evidence_types
    evidence = list(db.exec(
        select(EvidenceItem).where(EvidenceItem.task_id == task.id).order_by(EvidenceItem.added_at.desc())
    ).all())
    return {
        "task": task,
        "template": template,
        "display_name": get_task_display_name(task, template),
        "evidence": evidence,
        "get_evidence_types": get_evidence_types,
        "created_at": datetime.now(),
    }


def get_or_create_memo_doc(db: Session, task_id: int) -> Optional[GeneratedDocument]:
    """Get latest memo GeneratedDocument for task, or None."""
    q = select(GeneratedDocument).where(
        GeneratedDocument.task_id == task_id,
        GeneratedDocument.doc_type == "memo",
    ).order_by(GeneratedDocument.updated_at.desc())
    return db.exec(q).first()


def save_memo_content(db: Session, task_id: int, content: dict[str, str]) -> GeneratedDocument:
    """Save memo content to GeneratedDocument. Creates or updates."""
    existing = get_or_create_memo_doc(db, task_id)
    task = db.get(TaskInstance, task_id)
    template = db.get(TaskTemplate, task.template_id) if task else None
    title = f"Compliance Memo — {get_task_display_name(task, template)}"
    content_json = json.dumps(content)
    now = datetime.utcnow()
    if existing:
        existing.content_json = content_json
        existing.title = title
        existing.updated_at = now
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    doc = GeneratedDocument(
        task_id=task_id,
        doc_type="memo",
        title=title,
        content_json=content_json,
        updated_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def load_memo_content(doc: Optional[GeneratedDocument]) -> dict[str, str]:
    """Parse content_json from memo doc."""
    if not doc or not doc.content_json:
        return {"context": "", "actions_taken": "", "decision": "", "risks": "", "date": datetime.now().strftime("%Y-%m-%d")}
    try:
        d = json.loads(doc.content_json)
        return {
            "context": d.get("context", ""),
            "actions_taken": d.get("actions_taken", ""),
            "decision": d.get("decision", ""),
            "risks": d.get("risks", ""),
            "date": d.get("date", datetime.now().strftime("%Y-%m-%d")),
        }
    except json.JSONDecodeError:
        return {"context": "", "actions_taken": "", "decision": "", "risks": "", "date": datetime.now().strftime("%Y-%m-%d")}
