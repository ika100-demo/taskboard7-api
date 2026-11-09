"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from taskboard7_api.main import app


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """URL of a throw-away Postgres: TEST_DATABASE_URL, else a testcontainers container."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        os.environ["DATABASE_URL"] = url
        yield url
        return
    from testcontainers.postgres import PostgresContainer  # lazy: dev dependency

    with PostgresContainer("postgres:16-alpine", driver=None) as container:
        url = container.get_connection_url()
        os.environ["DATABASE_URL"] = url
        yield url


@pytest.fixture()
def clean_database(database_url: str) -> str:
    """The database URL with an empty schema for this test."""
    import psycopg  # lazy: runtime dependency added by the implementation

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS tasks")
    return database_url


@pytest.fixture()
def client(request: pytest.FixtureRequest) -> TestClient:
    """A TestClient for the FastAPI application.

    /ready checks the database, so the readiness test gets a real DATABASE_URL.
    """
    if request.node.name == "test_ready_returns_ready":
        request.getfixturevalue("database_url")
    return TestClient(app)
