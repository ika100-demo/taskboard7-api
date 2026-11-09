"""Acceptance tests for spec 002-store-tasks-in-postgres-so-they-survive."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Iterator
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from taskboard7_api.main import app

UNAVAILABLE = {"detail": "Database unavailable"}


def _closed_port_url() -> str:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"postgresql://u:p@127.0.0.1:{port}/db"


def _use(url: str) -> None:
    """Point the running app at a fresh Database + PostgresTaskStore for url.

    A new instance as far as state is concerned: a restart or a second process.
    """
    from taskboard7_api.db import Database, get_database
    from taskboard7_api.tasks.pg_store import PostgresTaskStore
    from taskboard7_api.tasks.store import get_task_store

    database = Database(url)
    store = PostgresTaskStore(database)
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_task_store] = lambda: store


@pytest.fixture()
def use_db(clean_database: str) -> Iterator[Callable[[str], None]]:
    try:
        yield _use
    finally:
        app.dependency_overrides.clear()


def _create(c: TestClient, title: str, due: str | None = None) -> dict:
    r = c.post("/tasks", json={"title": title, "due_date": due})
    assert r.status_code == 201, r.text
    return r.json()


def test_tasks_survive_restart(use_db, database_url: str) -> None:  # AC-002.1
    c = TestClient(app)
    use_db(database_url)
    created = [_create(c, "A", "2026-12-01"), _create(c, "B"), _create(c, "C", "2027-01-02")]
    use_db(database_url)  # restart: new Database and store, same database
    r = c.get("/tasks")
    assert r.status_code == 200
    assert r.json() == created


def test_second_instance_sees_task(use_db, database_url: str) -> None:  # AC-002.2
    c = TestClient(app)
    use_db(database_url)
    created = _create(c, "Shared", "2026-12-24")
    use_db(database_url)  # the other instance
    assert c.get("/tasks").json() == [created]


def test_post_shape_and_null_due_date(use_db, database_url: str) -> None:  # AC-002.3
    c = TestClient(app)
    use_db(database_url)
    body = _create(c, "Buy milk", "2026-12-01")
    assert set(body) == {"id", "title", "due_date"}
    assert body["due_date"] == "2026-12-01"
    assert _create(c, "No date")["due_date"] is None


def test_validation_422_and_nothing_stored(use_db, database_url: str) -> None:  # AC-002.3
    c = TestClient(app)
    use_db(database_url)
    r = c.post("/tasks", json={"title": ""})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "title"]
    r = c.post("/tasks", json={"title": "x", "due_date": "2026-02-30"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "due_date"]
    assert c.get("/tasks").json() == []


def test_list_order_empty_and_distinct_ids(use_db, database_url: str) -> None:  # AC-002.3
    c = TestClient(app)
    use_db(database_url)
    assert c.get("/tasks").json() == []
    first = _create(c, "Same")
    second = _create(c, "Same")
    third = _create(c, "Other")
    assert first["id"] != second["id"]
    assert c.get("/tasks").json() == [first, second, third]


def test_unreachable_database_returns_503(use_db, database_url: str) -> None:  # AC-002.4
    c = TestClient(app)
    use_db(_closed_port_url())
    start = time.monotonic()
    r = c.post("/tasks", json={"title": "lost"})
    assert time.monotonic() - start < 5
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == UNAVAILABLE
    start = time.monotonic()
    r = c.get("/tasks")
    assert time.monotonic() - start < 5
    assert r.status_code == 503
    assert r.json() == UNAVAILABLE
    use_db(database_url)
    assert c.get("/tasks").json() == []  # nothing stored by the failed POST


def test_invalid_input_is_422_even_when_database_down(use_db) -> None:  # AC-002.4
    c = TestClient(app)
    use_db(_closed_port_url())
    assert c.post("/tasks", json={"title": ""}).status_code == 422


def test_ready_503_when_database_down_health_ok(use_db) -> None:  # AC-002.5
    c = TestClient(app)
    use_db(_closed_port_url())
    r = c.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "not ready"}
    h = c.get("/health")
    assert h.status_code == 200
    assert h.json() == {"status": "ok"}


def test_ready_200_when_database_up(use_db, database_url: str) -> None:  # AC-002.5
    c = TestClient(app)
    use_db(database_url)
    r = c.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_recovers_without_restart(use_db, database_url: str) -> None:  # AC-002.6
    c = TestClient(app)
    use_db(_closed_port_url())
    assert c.get("/ready").status_code == 503
    assert c.get("/tasks").status_code == 503
    use_db(database_url)  # database is back; the app itself is not re-imported
    assert c.get("/ready").status_code == 200
    created = _create(c, "after recovery")
    assert c.get("/tasks").json() == [created]
