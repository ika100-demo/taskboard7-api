---
spec_id: 002-store-tasks-in-postgres-so-they-survive
shape: service-python
spec_hash: 8ba0eb5763fd
summary: Replace the in-memory task store with Postgres (psycopg 3, lazy connect, 503 on DB outage, DB-backed /ready)
tasks:
  - id: t1
    title: Add the Database module (psycopg, timeouts, schema bootstrap, ping) and dependencies
    files: [src/taskboard7_api/db.py, pyproject.toml, uv.lock]
    covers: [AC-002.1, AC-002.4, AC-002.5, AC-002.6]
    parallel_safe: true
    depends_on: []
    done: true
  - id: t2
    title: Add PostgresTaskStore and wire it behind get_task_store
    files: [src/taskboard7_api/tasks/pg_store.py, src/taskboard7_api/tasks/store.py]
    covers: [AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.6]
    parallel_safe: true
    depends_on: [t1]
  - id: t3
    title: Map DatabaseUnavailableError to 503 and make /ready check the database
    files: [src/taskboard7_api/main.py, docs/env-vars.md]
    covers: [AC-002.4, AC-002.5, AC-002.6]
    parallel_safe: true
    depends_on: [t1]
---

# Plan — 002 Store tasks in Postgres so they survive restarts and are shared between instances

Interfaces, contract, schema and test wiring: [design.md](design.md); decision record:
[ADR-001](../../adr/001-postgres-with-psycopg.md). t1 first; t2 and t3 both import only from `db.py` and touch
disjoint files, so they run in parallel. Router and models are not changed. No gitops change: the system plan
already wires `uses: postgres` (`DATABASE_URL`) and the probes already hit `/health` and `/ready`.

## t1 — Add the Database module (psycopg, timeouts, schema bootstrap, ping) and dependencies

**Files:** src/taskboard7_api/db.py, pyproject.toml, uv.lock
**Covers:** AC-002.1, AC-002.4, AC-002.5, AC-002.6
**Goal:** One module owns every database concern: building bounded connections from `DATABASE_URL`, creating the
`tasks` table once, translating driver failures into `DatabaseUnavailableError`, and a bounded readiness ping. Nothing
connects at import time.

**Implementation notes:**
- `pyproject.toml`: add `psycopg[binary]>=3.2` to `dependencies` and `testcontainers[postgres]>=4.8` to the `dev`
  extra; regenerate `uv.lock` through `devbox shell` / `devbox run` (its init hook runs `uv sync`), never `uv add`.
- Constants and signatures exactly as in design.md (`CONNECT_TIMEOUT_S = 2`, `STATEMENT_TIMEOUT_MS = 3000`,
  `READY_TIMEOUT_S = 1.0`).
- `Database.connection()`: `psycopg.connect(url, connect_timeout=2, options="-c statement_timeout=3000")`; empty or
  `None` url raises `DatabaseUnavailableError` without trying. Commit on clean exit, rollback on exception, always
  close. Catch `psycopg.OperationalError` and `psycopg.InterfaceError` (covers refused, auth, `QueryCanceled`
  timeouts, dropped connections) and raise `DatabaseUnavailableError` from them; let other errors propagate.
- Schema bootstrap on the first successful connect per `Database` instance, guarded by a `threading.Lock` and a
  flag: one transaction with `SELECT pg_advisory_xact_lock(<fixed constant>)` then the `CREATE TABLE IF NOT EXISTS
  tasks (...)` from design.md; set the flag only after commit, so a failed bootstrap is retried on the next request.
- `ping(timeout)`: run connect + `SELECT 1` in a daemon worker thread (or an executor shut down with `wait=False`)
  and wait at most `timeout`; return `False` on timeout or any error, never raise.
- `get_database()`: module singleton created on first call from `os.environ.get("DATABASE_URL")`.
- Log `database_unavailable` (warning, `error`=exception class name, `operation`) via structlog; never log the URL.
- mypy strict, no `# type: ignore` without reason; bandit-clean (parameterised SQL only).

**Done when:** `Database` against a reachable Postgres creates the table and pings `True`; against a closed port
raises `DatabaseUnavailableError` / pings `False` within the bounds; `devbox run quality` is green. The HTTP
acceptance tests pass after t2 and t3.

## t2 — Add PostgresTaskStore and wire it behind get_task_store

**Files:** src/taskboard7_api/tasks/pg_store.py, src/taskboard7_api/tasks/store.py
**Covers:** AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.6
**Goal:** Tasks are stored in and read from the `tasks` table, oldest first by `seq`, with the same `Task` objects
as before, so restarts and a second instance see the same list.

**Implementation notes:**
- `PostgresTaskStore(database)`: `add` builds `id = str(uuid.uuid4())`, runs one
  `INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s)` inside `database.connection()` and returns
  `Task(id=..., title=title, due_date=due_date)`; never retries. `list` runs
  `SELECT id, title, due_date FROM tasks ORDER BY seq` and maps rows to `Task`. `clear` runs `TRUNCATE tasks`.
- Title stored verbatim (no trimming); `due_date` passed as `datetime.date` or `None`.
- `store.py`: keep the in-memory `TaskStore` class unchanged (spec 001 tests use it as an override); add the
  `TaskRepository` Protocol; `get_task_store()` returns a lazily created module singleton
  `PostgresTaskStore(get_database())`, annotated `-> TaskRepository`. Creating it must not connect.
- Do not touch `router.py` or `models.py`; `DatabaseUnavailableError` simply propagates to the app handler (t3).

**Done when:** acceptance tests for AC-002.1, AC-002.2 and AC-002.3 pass against the test Postgres (with t3 merged,
also AC-002.4 and AC-002.6); spec 001's tests in `tests/test_tasks.py` still pass.

## t3 — Map DatabaseUnavailableError to 503 and make /ready check the database

**Files:** src/taskboard7_api/main.py, docs/env-vars.md
**Covers:** AC-002.4, AC-002.5, AC-002.6
**Goal:** A database outage answers `503 {"detail": "Database unavailable"}` on task requests and
`503 {"status": "not ready"}` on `/ready`, while `/health` stays `200`, and both recover on their own.

**Implementation notes:**
- `@app.exception_handler(DatabaseUnavailableError)` returning `JSONResponse(status_code=503,
  content={"detail": "Database unavailable"})`. Do not add a validation handler (422 stays FastAPI's default).
- `/ready`: take `database: Database = Depends(get_database)` (tests override it); `database.ping()` true →
  `200 {"status": "ready"}`, else `JSONResponse(503, {"status": "not ready"})`. Keep `response_model=HealthResponse`
  for the 200 schema. No caching of the result.
- `/health`, `/ping`, `/metrics` unchanged; no database work at import or startup (no lifespan connect).
- `docs/env-vars.md`: add a "Database" section with `DATABASE_URL` (default unset → `/tasks` 503, `/ready` 503),
  note that the gitops `uses: postgres` injects it, the 2 s connect / 3 s statement / 1 s ready timeouts, and that
  tests use `TEST_DATABASE_URL` or testcontainers.

**Done when:** acceptance tests for AC-002.4, AC-002.5 and AC-002.6 pass (with t2 merged), the existing
`tests/test_health.py` passes against the test Postgres, and `devbox run ci` is green.
