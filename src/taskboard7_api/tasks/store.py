"""Thread-safe in-memory task store."""

import threading
import uuid
from datetime import date
from typing import Protocol

from taskboard7_api.db import get_database
from taskboard7_api.tasks.models import Task
from taskboard7_api.tasks.pg_store import PostgresTaskStore


class TaskStore:
    """Keeps tasks in creation order."""

    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._lock = threading.Lock()

    def add(self, title: str, due_date: date | None) -> Task:
        task = Task(id=str(uuid.uuid4()), title=title, due_date=due_date)
        with self._lock:
            self._tasks.append(task)
        return task

    def list(self) -> list[Task]:
        with self._lock:
            return list(self._tasks)

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()


class TaskRepository(Protocol):
    """What the router needs from a task store."""

    def add(self, title: str, due_date: date | None) -> Task: ...

    def list(self) -> list[Task]: ...

    def clear(self) -> None: ...


_store: TaskRepository | None = None
_store_lock = threading.Lock()


def get_task_store() -> TaskRepository:
    """Lazily created Postgres store; creating it does not connect."""
    global _store
    with _store_lock:
        if _store is None:
            _store = PostgresTaskStore(get_database())
        return _store
