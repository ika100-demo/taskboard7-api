"""Postgres-backed task store."""

import uuid
from datetime import date

from taskboard7_api.db import Database
from taskboard7_api.tasks.models import Task


class PostgresTaskStore:
    """Stores tasks in the `tasks` table, oldest first by `seq`."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, title: str, due_date: date | None) -> Task:
        task_id = str(uuid.uuid4())
        with self._database.connection() as conn:
            conn.execute(
                "INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s)",
                (task_id, title, due_date),
            )
        return Task(id=task_id, title=title, due_date=due_date)

    def list(self) -> list[Task]:
        with self._database.connection() as conn:
            rows = conn.execute("SELECT id, title, due_date FROM tasks ORDER BY seq").fetchall()
        return [Task(id=row[0], title=row[1], due_date=row[2]) for row in rows]

    def clear(self) -> None:
        with self._database.connection() as conn:
            conn.execute("TRUNCATE tasks")
