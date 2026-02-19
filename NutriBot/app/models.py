"""
SQLModel models for BCSD Child Nutrition Ops Console.
Phase 1: TaskTemplate, TaskInstance, ChecklistItem, NoteLog.
Phase 3: EvidenceRequirement, EvidenceItem, RetentionRule.
"""
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

# Controlled lists for evidence
EVIDENCE_TYPES = ("submission", "approval", "calculation", "source_data", "communication", "training", "policy", "other")
IMPORTANCE_LEVELS = ("required", "supporting", "nice_to_have")
RETENTION_DISPOSITION = ("keep", "review", "delete_candidate")


class TaskTemplate(SQLModel, table=True):
    """Recurring task template. Defines what tasks repeat each year."""
    __tablename__ = "task_template"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str  # e.g., Verification, Application, Training, Reporting
    recurrence_rule: str = ""  # e.g., "annual", "monthly", "quarterly"
    default_checklist: str = ""  # JSON or newline-separated default checklist items
    created_at: datetime = Field(default_factory=datetime.utcnow)

    evidence_requirements: list["EvidenceRequirement"] = Relationship(back_populates="template")
    task_instances: list["TaskInstance"] = Relationship(back_populates="template")
    data_fields: list["TaskDataField"] = Relationship(back_populates="template")


class EvidenceRequirement(SQLModel, table=True):
    """Defines what evidence is expected for tasks from a template."""
    __tablename__ = "evidence_requirement"

    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="task_template.id")
    evidence_type: str  # submission, approval, etc.
    importance: str  # required, supporting, nice_to_have
    description: str = ""

    template: Optional[TaskTemplate] = Relationship(back_populates="evidence_requirements")


class RetentionRule(SQLModel, table=True):
    """Rules to auto-suggest keep_until/review_date when evidence is added."""
    __tablename__ = "retention_rule"

    id: Optional[int] = Field(default=None, primary_key=True)
    category: str  # Verification, Claims, Procurement, etc.
    evidence_type: str = ""  # blank = any
    importance: str = ""  # blank = any
    years_to_keep: Optional[int] = None
    is_permanent: bool = False
    description: str = ""


class TaskInstance(SQLModel, table=True):
    """A task instance for a specific year. Created from a template."""
    __tablename__ = "task_instance"

    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="task_template.id")
    year: int
    month: Optional[int] = None  # 1-12 for MONTHLY instances; None for ANNUAL/ONCE
    due_date: Optional[date] = None
    status: str = "pending"  # pending, in_progress, completed
    notes: str = ""
    completion_date: Optional[date] = None  # Set when status becomes completed
    created_from_generation: bool = False  # True if created by Year Planner
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    template: Optional[TaskTemplate] = Relationship(back_populates="task_instances")
    checklist_items: list["ChecklistItem"] = Relationship(back_populates="task")
    note_logs: list["NoteLog"] = Relationship(back_populates="task")
    evidence_items: list["EvidenceItem"] = Relationship(back_populates="task")
    data_values: list["TaskDataValue"] = Relationship(back_populates="task")


class ChecklistItem(SQLModel, table=True):
    """Checklist item for a task instance."""
    __tablename__ = "checklist_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task_instance.id")
    text: str
    completed: bool = False
    sort_order: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    task: Optional[TaskInstance] = Relationship(back_populates="checklist_items")


class NoteLog(SQLModel, table=True):
    """Timestamped note for a task instance."""
    __tablename__ = "note_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task_instance.id")
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    task: Optional[TaskInstance] = Relationship(back_populates="note_logs")


DOC_TYPES = ("cover_sheet", "memo", "evidence_index", "export_cover")


class GeneratedDocument(SQLModel, table=True):
    """Generated document (cover sheet, memo, evidence index)."""
    __tablename__ = "generated_document"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: Optional[int] = Field(default=None, foreign_key="task_instance.id")
    doc_type: str  # cover_sheet, memo, evidence_index, export_cover
    title: str = ""
    content_json: str = ""  # memo inputs, doc parameters
    html_path: str = ""
    pdf_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceItem(SQLModel, table=True):
    """Evidence file attached to a task instance."""
    __tablename__ = "evidence_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task_instance.id")
    category: str = ""
    evidence_type: str  # primary type (first of evidence_types for multi-tag items)
    evidence_types_json: str = ""  # JSON array of types; one document can satisfy multiple requirements
    importance: str  # required, supporting, nice_to_have
    description: str = ""
    original_filename: str = ""
    stored_filename: str = ""
    file_path: str = ""  # canonical path relative to vault root
    added_at: datetime = Field(default_factory=datetime.utcnow)
    retention_rule_id: Optional[int] = Field(default=None, foreign_key="retention_rule.id")
    keep_until: Optional[date] = None
    review_date: Optional[date] = None
    disposition: str = "keep"  # keep, review, delete_candidate

    task: Optional[TaskInstance] = Relationship(back_populates="evidence_items")


class TaskDataField(SQLModel, table=True):
    """Structured data field definition for a template (e.g., monthly claim fields)."""
    __tablename__ = "task_data_field"

    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="task_template.id")
    field_key: str  # unique per template
    label: str
    data_type: str  # int, float, currency, percent, text, bool, date
    display_order: int = 0
    is_required: bool = False

    template: Optional[TaskTemplate] = Relationship(back_populates="data_fields")


class TaskDataValue(SQLModel, table=True):
    """Stored value for a task's structured data field."""
    __tablename__ = "task_data_value"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task_instance.id")
    field_key: str
    value_text: str = ""  # store as text; parse based on field data_type

    task: Optional[TaskInstance] = Relationship(back_populates="data_values")
