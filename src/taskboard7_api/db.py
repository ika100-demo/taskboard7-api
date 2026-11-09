"""Postgres access: bounded connections, schema bootstrap and a readiness ping."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import structlog

CONNECT_TIMEOUT_S = 2
STATEMENT_TIMEOUT_MS = 3000
READY_TIMEOUT_S = 1.0

_SCHEMA_LOCK_KEY = 727002

_CREATE_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    id       text   PRIMARY KEY,
    title    text   NOT NULL,
    due_date date   NULL,
    seq      bigint GENERATED ALWAYS AS IDENTITY
)
"""

logger = structlog.get_logger(__name__)


class DatabaseUnavailableError(Exception):
    """The database is unreachable, refused us, or too slow."""


class Database:
    """Owns every database concern for one DATABASE_URL."""

    def __init__(self, url: str | None) -> None:
        self._url = url
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def _connect(self, operation: str) -> psycopg.Connection:
        if not self._url:
            logger.warning("database_unavailable", error="NotConfigured", operation=operation)
            raise DatabaseUnavailableError("DATABASE_URL is not set")
        try:
            return psycopg.connect(
                self._url,
                connect_timeout=CONNECT_TIMEOUT_S,
                options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
            )
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            logger.warning("database_unavailable", error=type(exc).__name__, operation=operation)
            raise DatabaseUnavailableError("database unavailable") from exc

    def _ensure_schema(self, conn: psycopg.Connection) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_KEY,))
                conn.execute(_CREATE_TASKS)            self._schema_ready = True
            logger.info("task_schema_ready")

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        conn = self._connect("connect")
        try:
            try:
                self._ensure_schema(conn)
                yield conn
                conn.commit()
            except BaseException:
                try:
                    conn.rollback()
                except (psycopg.OperationalError, psycopg.InterfaceError):
                    pass
                raise
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            logger.warning("database_unavailable", error=type(exc).__name__, operation="query")
            raise DatabaseUnavailableError("database unavailable") from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001  # closing a broken connection must not mask errors
                pass

    def ping(self, timeout: float = READY_TIMEOUT_S) -> bool:
        """SELECT 1 bounded by `timeout` wall-clock seconds; never raises."""
        result: list[bool] = []

        def run() -> None:
            try:
                with self.connection() as conn:
                    conn.execute("SELECT 1")
                result.append(True)
            except Exception:  # noqa: BLE001  # ping reports failure, never raises
                result.append(False)

        worker = threading.Thread(target=run, daemon=True, name="db-ping")
        worker.start()
        worker.join(timeout)
        return bool(result) and result[0]


_database: Database | None = None
_database_lock = threading.Lock()


def get_database() -> Database:
    """Module singleton built from DATABASE_URL on first call."""
    global _database
    with _database_lock:
        if _database is None:
            _database = Database(os.environ.get("DATABASE_URL"))
        return _database
