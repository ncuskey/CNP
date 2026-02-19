"""
Structured task data: TaskDataField definitions, TaskDataValue storage.
Monthly claim fields for "Monthly Claim Submission" template.
"""
from typing import Any, Optional

from sqlmodel import Session, select

from app.models import TaskDataField, TaskDataValue, TaskInstance, TaskTemplate

# Monthly claim fields for "Monthly Claim Submission" template
CLAIM_FIELDS = [
    ("total_reimbursement", "Total Reimbursement", "currency", 0),
    ("free_meals", "Free Meals", "int", 1),
    ("reduced_meals", "Reduced Meals", "int", 2),
    ("paid_meals", "Paid Meals", "int", 3),
    ("breakfast_meals", "Breakfast Meals", "int", 4),
    ("adp", "ADP", "int", 5),
    ("claim_submitted_date", "Claim Submitted Date", "date", 6),
    ("claim_approved_date", "Claim Approved Date", "date", 7),
    ("adjustments_required", "Adjustments Required", "bool", 8),
]


def find_monthly_claim_template(db: Session) -> Optional[TaskTemplate]:
    """Find 'Monthly Claim Submission' template."""
    return db.exec(
        select(TaskTemplate).where(
            TaskTemplate.name == "Monthly Claim Submission",
            TaskTemplate.category == "Claims",
        )
    ).first()


def ensure_claim_fields(db: Session, template_id: int) -> int:
    """Ensure claim fields exist for template. Returns count added."""
    existing = {f.field_key for f in db.exec(
        select(TaskDataField).where(TaskDataField.template_id == template_id)
    ).all()}
    added = 0
    for field_key, label, data_type, display_order in CLAIM_FIELDS:
        if field_key not in existing:
            db.add(TaskDataField(
                template_id=template_id,
                field_key=field_key,
                label=label,
                data_type=data_type,
                display_order=display_order,
                is_required=False,
            ))
            added += 1
            existing.add(field_key)
    if added:
        db.commit()
    return added


def get_claim_fields_for_template(db: Session, template_id: int) -> list[TaskDataField]:
    """Get data fields for template, ordered by display_order."""
    return list(db.exec(
        select(TaskDataField).where(TaskDataField.template_id == template_id)
        .order_by(TaskDataField.display_order)
    ).all())


def get_task_values(db: Session, task_id: int) -> dict[str, str]:
    """Get all TaskDataValue for task as {field_key: value_text}."""
    vals = db.exec(select(TaskDataValue).where(TaskDataValue.task_id == task_id)).all()
    return {v.field_key: v.value_text for v in vals}


def save_task_data(db: Session, task_id: int, data: dict[str, Any]) -> None:
    """Upsert TaskDataValue records. Partial save supported."""
    for field_key, value in data.items():
        if field_key.startswith("_"):
            continue
        val_str = _to_value_text(value)
        existing = db.exec(
            select(TaskDataValue).where(
                TaskDataValue.task_id == task_id,
                TaskDataValue.field_key == field_key,
            )
        ).first()
        if existing:
            existing.value_text = val_str
        else:
            db.add(TaskDataValue(task_id=task_id, field_key=field_key, value_text=val_str))
    db.commit()


def _to_value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def save_backfill_data(db: Session, updates: list[dict[str, Any]]) -> None:
    """Save backfill updates. Each item: {task_id, field_key, value}."""
    for u in updates:
        task_id = u.get("task_id")
        field_key = u.get("field_key")
        if task_id is None or not field_key:
            continue
        val_str = _to_value_text(u.get("value"))
        existing = db.exec(
            select(TaskDataValue).where(
                TaskDataValue.task_id == task_id,
                TaskDataValue.field_key == field_key,
            )
        ).first()
        if existing:
            existing.value_text = val_str
        else:
            db.add(TaskDataValue(task_id=task_id, field_key=field_key, value_text=val_str))
    db.commit()
