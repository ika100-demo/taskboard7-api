"""Acceptance tests for spec 001-create-and-list-tasks."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from taskboard7_api.main import app


@pytest.fixture()
def tasks_client() -> Iterator[TestClient]:
    from taskboard7_api.tasks.store import TaskStore, get_task_store

    store = TaskStore()
    app.dependency_overrides[get_task_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_task_store, None)


def _locs(response) -> list[list]:
    return [entry["loc"] for entry in response.json()["detail"]]


def test_create_task_returns_201_with_fields(tasks_client: TestClient) -> None:  # AC-001.1
    r = tasks_client.post("/tasks", json={"title": "Buy milk", "due_date": "2026-12-01"})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "title", "due_date"}
    assert isinstance(body["id"], str) and body["id"]
    assert body["title"] == "Buy milk"
    assert body["due_date"] == "2026-12-01"


@pytest.mark.parametrize(
    "payload",
    [{"title": "Buy milk"}, {"title": "Buy milk", "due_date": None}],
)
def test_create_task_without_due_date(tasks_client: TestClient, payload: dict) -> None:  # AC-001.2
    r = tasks_client.post("/tasks", json=payload)
    assert r.status_code == 201
    assert r.json()["due_date"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": 123},
        {"title": True},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
    ],
)
def test_invalid_title_rejected(tasks_client: TestClient, payload: dict) -> None:  # AC-001.3
    r = tasks_client.post("/tasks", json=payload)
    assert r.status_code == 422
    assert ["body", "title"] in _locs(r)
    assert tasks_client.get("/tasks").json() == []


@pytest.mark.parametrize("due", ["tomorrow", "2026-02-30", "2026-12-01T10:00:00"])
def test_invalid_due_date_rejected(tasks_client: TestClient, due: str) -> None:  # AC-001.4
    r = tasks_client.post("/tasks", json={"title": "Buy milk", "due_date": due})
    assert r.status_code == 422
    assert ["body", "due_date"] in _locs(r)
    assert tasks_client.get("/tasks").json() == []


def test_list_in_creation_order(tasks_client: TestClient) -> None:  # AC-001.5
    created = [
        tasks_client.post("/tasks", json={"title": t, "due_date": d}).json()
        for t, d in [("A", "2026-01-01"), ("B", None), ("C", "2026-03-03")]
    ]
    r = tasks_client.get("/tasks")
    assert r.status_code == 200
    assert r.json() == created
    assert [t["title"] for t in r.json()] == ["A", "B", "C"]


def test_list_empty(tasks_client: TestClient) -> None:  # AC-001.6
    r = tasks_client.get("/tasks")
    assert r.status_code == 200
    assert r.json() == []


def test_duplicate_titles_get_distinct_ids(tasks_client: TestClient) -> None:  # AC-001.7
    for _ in range(2):
        assert tasks_client.post("/tasks", json={"title": "same"}).status_code == 201
    tasks = tasks_client.get("/tasks").json()
    assert len(tasks) == 2
    assert tasks[0]["id"] != tasks[1]["id"]
