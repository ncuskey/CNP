"""
Preset Library: load and install preset packs (TaskTemplates, EvidenceRequirements, RetentionRules).
Idempotent — safe to run multiple times.
"""
import json
from pathlib import Path
from typing import Any, Optional

from sqlmodel import Session, select

from app.database import DATA_DIR
from app.evidence import seed_retention_rules
from app.models import EvidenceRequirement, RetentionRule, TaskTemplate
from app.task_data import ensure_claim_fields

PRESETS_DIR = DATA_DIR / "presets"


def load_preset_pack(name: str) -> dict[str, Any]:
    """Load preset pack from data/presets/{name}.json."""
    path = PRESETS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Preset pack not found: {name}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_template(db: Session, name: str, category: str) -> Optional[TaskTemplate]:
    """Find TaskTemplate by name and category."""
    return db.exec(
        select(TaskTemplate).where(
            TaskTemplate.name == name,
            TaskTemplate.category == category,
        )
    ).first()


def find_or_create_template(
    db: Session,
    name: str,
    category: str,
    recurrence_rule: str,
    default_checklist: str,
) -> tuple[TaskTemplate, bool]:
    """Find or create TaskTemplate. Returns (template, created)."""
    existing = find_template(db, name, category)
    if existing:
        return existing, False
    template = TaskTemplate(
        name=name,
        category=category,
        recurrence_rule=recurrence_rule or "",
        default_checklist=default_checklist or "",
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template, True


def _requirement_exists(
    db: Session,
    template_id: int,
    evidence_type: str,
    importance: str,
    description: str,
) -> bool:
    """Check if EvidenceRequirement already exists."""
    existing = db.exec(
        select(EvidenceRequirement).where(
            EvidenceRequirement.template_id == template_id,
            EvidenceRequirement.evidence_type == evidence_type,
            EvidenceRequirement.importance == importance,
            EvidenceRequirement.description == (description or ""),
        )
    ).first()
    return existing is not None


def ensure_requirements(
    db: Session,
    template_id: int,
    reqs: list[dict[str, Any]],
) -> tuple[int, int]:
    """Ensure evidence requirements exist. Returns (added, skipped)."""
    added = 0
    skipped = 0
    for r in reqs:
        et = r.get("evidence_type", "other")
        imp = r.get("importance", "supporting")
        desc = r.get("description", "")
        if _requirement_exists(db, template_id, et, imp, desc):
            skipped += 1
            continue
        req = EvidenceRequirement(
            template_id=template_id,
            evidence_type=et,
            importance=imp,
            description=desc,
        )
        db.add(req)
        added += 1
    if added:
        db.commit()
    return added, skipped


def _retention_rule_exists(
    db: Session,
    category: str,
    evidence_type: str,
    importance: str,
    years_to_keep: Optional[int],
    is_permanent: bool,
    description: str,
) -> bool:
    """Check if RetentionRule already exists."""
    from sqlalchemy import and_
    conditions = [
        RetentionRule.category == category,
        RetentionRule.evidence_type == (evidence_type or ""),
        RetentionRule.importance == (importance or ""),
        RetentionRule.description == (description or ""),
        RetentionRule.is_permanent == is_permanent,
    ]
    if not is_permanent:
        if years_to_keep is None:
            conditions.append(RetentionRule.years_to_keep.is_(None))
        else:
            conditions.append(RetentionRule.years_to_keep == years_to_keep)
    q = select(RetentionRule).where(and_(*conditions))
    existing = db.exec(q).first()
    return existing is not None


def ensure_retention_rules(
    db: Session,
    rules: list[dict[str, Any]],
) -> tuple[int, int]:
    """Ensure retention rules exist. Returns (added, skipped)."""
    added = 0
    skipped = 0
    for r in rules:
        cat = r.get("category", "")
        et = r.get("evidence_type", "")
        imp = r.get("importance", "")
        ytk = r.get("years_to_keep")
        perm = r.get("is_permanent", False)
        desc = r.get("description", "")
        if _retention_rule_exists(db, cat, et, imp, ytk, perm, desc):
            skipped += 1
            continue
        rule = RetentionRule(
            category=cat,
            evidence_type=et,
            importance=imp,
            years_to_keep=ytk,
            is_permanent=perm,
            description=desc,
        )
        db.add(rule)
        added += 1
    if added:
        db.commit()
    return added, skipped


def preview_install(db: Session, pack: dict[str, Any]) -> dict[str, Any]:
    """Preview what would be added/skipped. Returns summary dict."""
    templates_to_add: list[dict] = []
    templates_to_skip: list[dict] = []
    requirements_to_add = 0
    requirements_to_skip = 0
    retention_to_add = 0
    retention_to_skip = 0

    for t in pack.get("templates", []):
        name = t.get("name", "")
        category = t.get("category", "")
        existing = find_template(db, name, category)
        if existing:
            templates_to_skip.append({"name": name, "category": category})
            reqs = t.get("evidence_requirements", [])
            for r in reqs:
                if _requirement_exists(
                    db, existing.id,
                    r.get("evidence_type", "other"),
                    r.get("importance", "supporting"),
                    r.get("description", ""),
                ):
                    requirements_to_skip += 1
                else:
                    requirements_to_add += 1
        else:
            templates_to_add.append({"name": name, "category": category})
            requirements_to_add += len(t.get("evidence_requirements", []))

    for r in pack.get("retention_rules", []):
        if _retention_rule_exists(
            db,
            r.get("category", ""),
            r.get("evidence_type", ""),
            r.get("importance", ""),
            r.get("years_to_keep"),
            r.get("is_permanent", False),
            r.get("description", ""),
        ):
            retention_to_skip += 1
        else:
            retention_to_add += 1

    return {
        "templates_to_add": templates_to_add,
        "templates_to_skip": templates_to_skip,
        "requirements_to_add": requirements_to_add,
        "requirements_to_skip": requirements_to_skip,
        "retention_to_add": retention_to_add,
        "retention_to_skip": retention_to_skip,
        "notes": "Install is idempotent. Existing items (matched by name+category, template_id+evidence_type+importance+description, or retention rule fields) are skipped.",
    }


def install_pack(db: Session, pack: dict[str, Any]) -> dict[str, Any]:
    """Install preset pack. Returns summary of added/skipped counts."""
    seed_retention_rules(db)

    added_templates = 0
    skipped_templates = 0
    added_requirements = 0
    skipped_requirements = 0
    added_retention_rules = 0
    skipped_retention_rules = 0

    for t in pack.get("templates", []):
        name = t.get("name", "")
        category = t.get("category", "")
        recurrence = t.get("recurrence_rule", "")
        checklist = t.get("default_checklist", [])
        if isinstance(checklist, list):
            checklist_str = "\n".join(str(x) for x in checklist)
        else:
            checklist_str = str(checklist)

        template, created = find_or_create_template(db, name, category, recurrence, checklist_str)
        if created:
            added_templates += 1
        else:
            skipped_templates += 1

        reqs = t.get("evidence_requirements", [])
        a, s = ensure_requirements(db, template.id, reqs)
        added_requirements += a
        skipped_requirements += s

        if name == "Monthly Claim Submission" and category == "Claims":
            ensure_claim_fields(db, template.id)

    a, s = ensure_retention_rules(db, pack.get("retention_rules", []))
    added_retention_rules += a
    skipped_retention_rules += s

    return {
        "added_templates": added_templates,
        "skipped_templates": skipped_templates,
        "added_requirements": added_requirements,
        "skipped_requirements": skipped_requirements,
        "added_retention_rules": added_retention_rules,
        "skipped_retention_rules": skipped_retention_rules,
    }


def list_available_packs() -> list[str]:
    """List available preset pack names (without .json)."""
    if not PRESETS_DIR.exists():
        return []
    return [p.stem for p in PRESETS_DIR.glob("*.json")]
