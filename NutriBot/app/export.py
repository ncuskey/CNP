"""
Audit packet export: folder + index file.
"""
import shutil
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from app.database import VAULT_DIR
from app.evidence import compute_missing_evidence, get_evidence_types, get_task_display_name, get_vault_path
from app.models import EvidenceItem, TaskInstance, TaskTemplate


def export_task_packet(
    task: TaskInstance,
    evidence: list[EvidenceItem],
    db: Session,
    include_nice_to_have: bool = False,
    include_generated: bool = False,
) -> Path:
    """
    Create audit packet folder for a task.
    Copies evidence files, generates index.html.
    Returns path to created folder.
    """
    packets_dir = VAULT_DIR / "_audit_packets" / str(task.year)
    packets_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{get_task_display_name(task, task.template)}_{ts}".replace(" ", "_")
    out_dir = packets_dir / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Filter evidence
    if not include_nice_to_have:
        evidence = [e for e in evidence if e.importance != "nice_to_have"]

    # Copy files
    for e in evidence:
        src = VAULT_DIR / e.file_path
        if src.exists():
            shutil.copy2(src, out_dir / e.stored_filename)

    # Copy generated docs if requested
    if include_generated:
        gen_dir = get_vault_path(task, task.template) / "_generated"
        if gen_dir.exists():
            gen_out = out_dir / "_generated"
            gen_out.mkdir(exist_ok=True)
            for f in gen_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, gen_out / f.name)

    # Generate index
    missing_req, missing_sup = compute_missing_evidence(db, task, task.template)

    index_lines = [
        f"# Audit Packet: {task.template.name if task.template else 'Task'} ({task.year})",
        f"Generated: {datetime.now().isoformat()}",
        "",
        f"**Task:** {get_task_display_name(task, task.template)}",
        f"**Due Date:** {task.due_date or 'N/A'}",
        f"**Status:** {task.status}",
        "",
        "## Notes Summary",
        task.notes or "(none)",
        "",
        "## Evidence",
    ]
    for e in evidence:
        index_lines.append(f"- {e.original_filename} ({', '.join(get_evidence_types(e))}, {e.importance})")
    index_lines.extend([
        "",
        "## Missing Requirements",
        f"- Required: {missing_req}",
        f"- Supporting: {missing_sup}",
    ])
    (out_dir / "index.md").write_text("\n".join(index_lines), encoding="utf-8")

    # Also write HTML index
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Audit Packet</title></head><body>
<h1>Audit Packet: {task.template.name if task.template else 'Task'} ({task.year})</h1>
<p>Generated: {datetime.now().isoformat()}</p>
<h2>Task</h2>
<p><strong>{get_task_display_name(task, task.template)}</strong><br>
Due: {task.due_date or 'N/A'} | Status: {task.status}</p>
<h2>Notes</h2>
<pre>{task.notes or '(none)'}</pre>
<h2>Evidence</h2>
<ul>
"""
    for e in evidence:
        html += f'<li><a href="{e.stored_filename}">{e.original_filename}</a> ({", ".join(get_evidence_types(e))}, {e.importance})</li>\n'
    html += f"""</ul>
<h2>Missing Requirements</h2>
<p>Required: {missing_req} | Supporting: {missing_sup}</p>
</body></html>"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    return out_dir


def export_year_category_packet(
    db: Session, year: int, category: str, include_generated: bool = False
) -> Path:
    """Export all tasks for year+category into one packet."""
    from app.models import TaskInstance, TaskTemplate
    q = select(TaskInstance).where(TaskInstance.year == year)
    tasks = list(db.exec(q).all())
    for t in tasks:
        t.template = db.get(TaskTemplate, t.template_id)
    tasks = [t for t in tasks if t.template and t.template.category == category]
    if not tasks:
        raise ValueError(f"No tasks for year={year} category={category}")

    packets_dir = VAULT_DIR / "_audit_packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{year}_{category}_{ts}".replace(" ", "_")
    out_dir = packets_dir / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    index_lines = [
        f"# Audit Packet: {year} - {category}",
        f"Generated: {datetime.now().isoformat()}",
        "",
        "## Tasks",
    ]
    for task in tasks:
        evidence = list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == task.id)).all())
        task_dir = out_dir / get_task_display_name(task, task.template).replace(" ", "_")
        task_dir.mkdir(exist_ok=True)
        for e in evidence:
            src = VAULT_DIR / e.file_path
            if src.exists():
                shutil.copy2(src, task_dir / e.stored_filename)
        if include_generated:
            gen_dir = get_vault_path(task, task.template) / "_generated"
            if gen_dir.exists():
                gen_out = task_dir / "_generated"
                gen_out.mkdir(exist_ok=True)
                for f in gen_dir.iterdir():
                    if f.is_file():
                        shutil.copy2(f, gen_out / f.name)
        missing_req, missing_sup = compute_missing_evidence(db, task, task.template)
        index_lines.append(f"\n### {get_task_display_name(task, task.template)}")
        index_lines.append(f"- Due: {task.due_date or 'N/A'} | Status: {task.status}")
        index_lines.append(f"- Evidence: {len(evidence)} | Missing required: {missing_req}")
        for e in evidence:
            index_lines.append(f"  - {e.original_filename}")

    (out_dir / "index.md").write_text("\n".join(index_lines), encoding="utf-8")
    return out_dir
