"""Request and response models for tasks."""

import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, StrictStr, field_validator

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TaskCreate(BaseModel):
    """Payload for creating a task."""

    title: StrictStr = Field(min_length=1, max_length=200)
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must contain a non-whitespace character")
        return value

    @field_validator("due_date", mode="before")
    @classmethod
    def _strict_due_date(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str) and _DATE_RE.match(value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise ValueError("due_date must be a YYYY-MM-DD calendar date")


class Task(BaseModel):
    """A stored task."""

    id: str
    title: str
    due_date: date | None
