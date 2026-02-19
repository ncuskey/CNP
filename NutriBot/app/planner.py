"""
Year Planner: generate TaskInstances from templates using recurrence rules.
Idempotent: does not create duplicates.
"""
from datetime import date
from typing import Optional

from sqlmodel import Session, select

from app.models import TaskInstance, TaskTemplate
from app.recurrence import compute_due_date, get_monthly_due_dates, parse_recurrence_rule


def generate_year_plan(
    db: Session,
    year: int,
    include_monthly: bool = True,
    include_no_recurrence: bool = False,
) -> dict:
    """
    Generate TaskInstances for all templates for the given year.
    Returns: {created, skipped, already_existed, errors}
    """
    result = {"created": 0, "skipped": 0, "already_existed": 0, "errors": []}
    templates = db.exec(select(TaskTemplate)).all()

    for tpl in templates:
        rule = (tpl.recurrence_rule or "").strip()
        rule_type, params = parse_recurrence_rule(rule)

        # Skip templates without recurrence unless include_no_recurrence
        if not rule_type and not include_no_recurrence:
            result["skipped"] += 1
            continue

        if rule_type in ("MONTHLY", "MONTHLY_NEXT"):
            if not include_monthly:
                result["skipped"] += 1
                continue
            for month, due_d in get_monthly_due_dates(rule, year):
                if _exists(db, tpl.id, year, month):
                    result["already_existed"] += 1
                    continue
                try:
                    inst = TaskInstance(
                        template_id=tpl.id,
                        year=year,
                        month=month,
                        due_date=due_d,
                        status="pending",
                        created_from_generation=True,
                    )
                    db.add(inst)
                    result["created"] += 1
                except Exception as e:
                    result["errors"].append(f"{tpl.name} {year}-{month:02d}: {e}")

        elif rule_type == "ANNUAL":
            due_d = compute_due_date(rule, year)
            if _exists(db, tpl.id, year, None):
                result["already_existed"] += 1
                continue
            try:
                inst = TaskInstance(
                    template_id=tpl.id,
                    year=year,
                    due_date=due_d,
                    status="pending",
                    created_from_generation=True,
                )
                db.add(inst)
                result["created"] += 1
            except Exception as e:
                result["errors"].append(f"{tpl.name} {year}: {e}")

        elif rule_type == "ONCE":
            due_d = params.get("date") if params else None
            if not due_d:
                result["skipped"] += 1
                continue
            if due_d.year != year:
                result["skipped"] += 1
                continue
            if _exists(db, tpl.id, due_d.year, None):
                result["already_existed"] += 1
                continue
            try:
                inst = TaskInstance(
                    template_id=tpl.id,
                    year=due_d.year,
                    due_date=due_d,
                    status="pending",
                    created_from_generation=True,
                )
                db.add(inst)
                result["created"] += 1
            except Exception as e:
                result["errors"].append(f"{tpl.name} {due_d.year}: {e}")

        else:
            # No recurrence - skip unless include_no_recurrence
            if include_no_recurrence:
                if _exists(db, tpl.id, year, None):
                    result["already_existed"] += 1
                else:
                    inst = TaskInstance(
                        template_id=tpl.id,
                        year=year,
                        status="pending",
                        created_from_generation=True,
                    )
                    db.add(inst)
                    result["created"] += 1
            else:
                result["skipped"] += 1

    db.commit()
    return result


def _exists(db: Session, template_id: int, year: int, month: Optional[int]) -> bool:
    """Check if a task instance already exists for template+year(+month)."""
    q = select(TaskInstance).where(
        TaskInstance.template_id == template_id,
        TaskInstance.year == year,
    )
    if month is not None:
        q = q.where(TaskInstance.month == month)
    else:
        q = q.where(TaskInstance.month.is_(None))
    return db.exec(q).first() is not None
