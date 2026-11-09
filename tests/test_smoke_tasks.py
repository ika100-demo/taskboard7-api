"""Smoke tests for spec 001 (AC-001.1, AC-001.6): reach the service only via its URL."""

from __future__ import annotations

import uuid

import httpx
import pytest


@pytest.mark.smoke
@pytest.mark.writes
def test_smoke_ac_001_1_create_task(smoke_base_url: str) -> None:  # AC-001.1
    title = f"smoke-{uuid.uuid4()}"
    r = httpx.post(
        smoke_base_url + "/tasks",
        json={"title": title, "due_date": "2026-12-01"},
        timeout=10,
    )
    assert r.status_code == 201
    body = r.json()
    assert isinstance(body["id"], str) and body["id"]
    assert body["title"] == title
    assert body["due_date"] == "2026-12-01"


@pytest.mark.smoke
def test_smoke_ac_001_6_list_tasks_is_json_array(smoke_base_url: str) -> None:  # AC-001.6
    r = httpx.get(smoke_base_url + "/tasks", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.smoke
def test_smoke_ac_001_1_rejects_invalid_input(smoke_base_url: str) -> None:  # AC-001.1 read-only
    r = httpx.post(smoke_base_url + "/tasks", json={"title": ""}, timeout=10)
    assert r.status_code == 422
