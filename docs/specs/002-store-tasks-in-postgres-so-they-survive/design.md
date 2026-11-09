# Design — 002 Store tasks in Postgres so they survive restarts and are shared between instances

## Decisions

- **psycopg 3, plain SQL, one short-lived connection per operation, schema created on first successful connection.**
  Reasons and consequences: [ADR-001](../../adr/001-postgres-with-psycopg.md). The contract's "(pooled)" is met in
  spirit (each request gets a fresh, bounded connection attempt and fails fast; recovery is immediate on the next
  request); a pool can later replace `Database.connection()` without changing callers (AC-002.4, AC-002.6).
- **Lazy everything.** Importing the app and starting the process never touch the database. `DATABASE_URL` is read
  when the `Database` singleton is first created (first request). Unset `DATABASE_URL` behaves like an unreachable
  database: `503` on `/tasks`, not ready on `/ready`, `/health` 200 (AC-002.5, AC-002.6).
- **Router and models stay unchanged** (spec note). The `503` comes from an app-level exception handler for
  `DatabaseUnavailableError` registered in `main.py`, not from code in the router. Validation still runs before the
  handler, so invalid input answers `422` even when the database is down.
- **`get_task_store()` returns the Postgres store.** The in-memory `TaskStore` class stays in `store.py` unchanged as a
  test double (spec 001's tests instantiate it through a dependency override); a `TaskRepository` Protocol names the
  interface both satisfy.
- **No retries.** An insert is executed once; any failure is `503` and the transaction is never committed, so no task
  is stored (AC-002.4).

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `src/taskboard7_api/db.py` | `Database` (connection factory with timeouts, schema bootstrap, `ping`), `DatabaseUnavailableError`, `get_database()` | new |
| `src/taskboard7_api/tasks/pg_store.py` | `PostgresTaskStore` (insert / list ordered by `seq` / clear) | new |
| `src/taskboard7_api/tasks/store.py` | adds `TaskRepository` Protocol; `get_task_store()` returns the `PostgresTaskStore` singleton; in-memory `TaskStore` kept | changed |
| `src/taskboard7_api/main.py` | `DatabaseUnavailableError` → 503 handler; `/ready` checks the database | changed |
| `src/taskboard7_api/tasks/router.py`, `tasks/models.py` | — | unchanged |
| `pyproject.toml`, `uv.lock` | `psycopg[binary]>=3.2`; dev: `testcontainers[postgres]>=4.8` | changed |
| `docs/env-vars.md` | `DATABASE_URL` | changed |

### Python interfaces (binding for tests and coders)

```python
# db.py
CONNECT_TIMEOUT_S = 2
STATEMENT_TIMEOUT_MS = 3000
READY_TIMEOUT_S = 1.0

class DatabaseUnavailableError(Exception): ...      # the only error callers see for an unreachable/slow DB

class Database:
    def __init__(self, url: str | None) -> None: ...  # url None/"" -> every call raises DatabaseUnavailableError
    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]: ...
        # psycopg.connect(url, connect_timeout=2, options="-c statement_timeout=3000");
        # on first success per instance: ensure_schema(); commits on clean exit, rolls back on error, always closes;
        # psycopg.OperationalError / psycopg.InterfaceError (incl. QueryCanceled) -> DatabaseUnavailableError
    def ping(self, timeout: float = READY_TIMEOUT_S) -> bool: ...
        # SELECT 1 bounded by `timeout` wall-clock (libpq/psycopg treat connect_timeout < 2 as 2, so run the
        # attempt in a worker thread and wait at most `timeout`); never raises; True only on success

def get_database() -> Database: ...                  # module singleton, built from os.environ["DATABASE_URL"] on first call

# tasks/store.py
class TaskRepository(Protocol):
    def add(self, title: str, due_date: date | None) -> Task: ...
    def list(self) -> list[Task]: ...
    def clear(self) -> None: ...

class TaskStore: ...                                 # unchanged in-memory implementation (test double)

def get_task_store() -> TaskRepository: ...          # module singleton PostgresTaskStore(get_database())

# tasks/pg_store.py
class PostgresTaskStore:
    def __init__(self, database: Database) -> None: ...
    def add(self, title: str, due_date: date | None) -> Task: ...  # id = str(uuid.uuid4()); one INSERT, no retry
    def list(self) -> list[Task]: ...                              # SELECT id, title, due_date FROM tasks ORDER BY seq
    def clear(self) -> None: ...                                   # TRUNCATE tasks (test hook)
```

**Test wiring (for the testers):** tests get a throw-away Postgres from `testcontainers[postgres]` in a session
fixture in `tests/conftest.py`, or use `TEST_DATABASE_URL` when set. The fixture must set `DATABASE_URL` before the
first request, because the existing `tests/test_health.py::test_ready_returns_ready` and the spec 001 HTTP tests
then run against a real database. Per-test isolation: `get_task_store().clear()`, or override `get_task_store` /
`get_database` with instances built on the container URL. "Process restarted" (AC-002.1) and "two instances"
(AC-002.2) can be simulated in-process with fresh `Database` + `PostgresTaskStore` instances on the same URL served
through a dependency override, or with real `uvicorn` subprocesses. "Database unreachable" (AC-002.4 to AC-002.6):
override `get_database` with `Database("postgresql://u:p@127.0.0.1:<closed port>/db")` (refused immediately), or
stop/start the container; recovery means swapping the override back to a reachable URL on the same running app
without re-importing it, or restarting the container on a fixed port.

## Contract

Unchanged from spec 001 for `POST /tasks` and `GET /tasks` request/response shapes, `201`, `200`, ordering and the
`422` validation body (AC-002.3). Additions:

- `POST /tasks`, `GET /tasks` → `503 Service Unavailable`, `Content-Type: application/json`, body exactly
  `{"detail": "Database unavailable"}`, when the database is unreachable, refuses auth, or a statement exceeds 3 s.
  Answered within 5 s (connect ≤ 2 s + statement ≤ 3 s). Nothing is stored (AC-002.4). A `422` is still returned for
  invalid input regardless of the database.
- `GET /ready` → `200 {"status": "ready"}` when `SELECT 1` succeeds within 1 s; otherwise
  `503 {"status": "not ready"}` (AC-002.5). Checked fresh on every call; no cached state, so it turns ready again as
  soon as the database is back (AC-002.6).
- `GET /health` → `200 {"status": "ok"}` always (AC-002.5). `/ping`, `/metrics` unchanged.

## Data

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id       text   PRIMARY KEY,                       -- uuid4 string
    title    text   NOT NULL,
    due_date date   NULL,
    seq      bigint GENERATED ALWAYS AS IDENTITY        -- "oldest first" = ORDER BY seq
);
```

Bootstrap runs in one transaction: `SELECT pg_advisory_xact_lock(<fixed 64-bit constant>)` then the `CREATE TABLE IF
NOT EXISTS`, so two instances starting together do not collide on the catalog. Runs once per `Database` instance after
its first successful connect (guarded by a lock + flag); if it fails, the flag stays unset and the next request tries
again. Tasks held in memory by the old version are not carried over (spec note).

## Logging

- `database_unavailable` (warning) with `error` = exception class name and `operation` (`add`, `list`, `ready`);
  never the URL, credentials or task title.
- `task_schema_ready` (info) once per process.

## Risks

- **Test suite needs Docker** (testcontainers) on CI and locally; GitHub-hosted runners have it. Self-hosted runners
  without Docker can set `TEST_DATABASE_URL`.
- **Connection per request** costs a handshake each time; acceptable at this scale (ADR-001).
- **Coverage gate (80 %)**: the unreachable-database paths must be exercised by tests, which the AC-002.4/5/6 tests do.
