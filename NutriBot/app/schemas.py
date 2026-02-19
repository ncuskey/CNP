"""
Pydantic schemas for request/response validation.
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel


class TaskTemplateCreate(BaseModel):
    name: str
    category: str
    recurrence_rule: str = ""
    default_checklist: str = ""


class TaskInstanceCreate(BaseModel):
    template_id: int
    year: int
    due_date: Optional[date] = None


class TaskInstanceUpdate(BaseModel):
    due_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ChecklistItemCreate(BaseModel):
    text: str
    sort_order: int = 0


class NoteLogCreate(BaseModel):
    content: str
