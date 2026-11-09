# Verification — 002 Store tasks in Postgres so they survive restarts and are shared between instances

**Result:** pass
**Commit:** f9c092a · **Base:** 653ac52 · **Trace:** 6/6 criteria named by tests (`tests/test_task_persistence.py`)

Re-verification after `f9c092a`, which changed only `tests/test_task_persistence.py` (the AC-002.4 timing, a test change the user approved). No source file changed since the previous verification at `c0755c7`, so the code references below are the same.

| Criterion | Verdict | Tests | Implementation | Notes |
|---|---|---|---|---|
| AC-002.1 | met | `tests/test_task_persistence.py::test_tasks_survive_restart` | `src/taskboard7_api/tasks/pg_store.py:20` (insert), `:27` (`ORDER BY seq`); `src/taskboard7_api/db.py:19-26`, `:65` (schema) | The test creates A, B and C, then swaps in a fresh `Database` and `PostgresTaskStore` on the same URL (the in-process "restart" that design.md allows). It asserts `GET /tasks` is 200 and equals the three creation bodies in order (lines 57-61). |
| AC-002.2 | met | `tests/test_task_persistence.py::test_second_instance_sees_task` | `src/taskboard7_api/tasks/pg_store.py:27`; `src/taskboard7_api/tasks/store.py:49-55` | The second instance is a separate `Database` and store pair. The test asserts the list equals `[created]`, which compares id, title and due_date (line 69). |
| AC-002.3 | met | `test_post_shape_and_null_due_date`, `test_validation_422_and_nothing_stored`, `test_list_order_empty_and_distinct_ids` (all in `tests/test_task_persistence.py`); the spec 001 suite in `tests/test_tasks.py` | `src/taskboard7_api/tasks/pg_store.py:16-28`; `tasks/router.py` and `tasks/models.py` are unchanged (no diff) | The tests cover: 201 with exactly id, title and due_date; due_date null when absent; 422 with `loc` naming `title` and `due_date` and nothing stored; `[]` when empty; oldest first; distinct ids for equal titles. Remaining minor gap, same as before: the whitespace-only and 200-character rules run only against the in-memory override. Those rules are enforced by the unchanged Pydantic model before the store is reached. Storing the title verbatim goes through a parameterised `text` insert (`pg_store.py:20`). |
| AC-002.4 | met | `tests/test_task_persistence.py::test_unreachable_database_returns_503`, `::test_invalid_input_is_422_even_when_database_down` | `src/taskboard7_api/main.py:38-43` (handler: 503 with `{"detail": "Database unavailable"}`); `src/taskboard7_api/db.py:48-55` (2 s connect, 3 s statement timeout, driver error mapped to `DatabaseUnavailableError`), `:77-83` (rollback and mapping on query errors) | Now proven. Each request is timed on its own and asserted `< 5` s: POST at lines 107-109, GET at lines 113-115. The test also checks 503, a JSON content type and the exact body for both requests, and that no task from the failed POST exists once the database is back (line 119). Residual note, not a defect: the test uses a closed port (immediate refusal). A database that is unreachable by timeout is bounded by the 2 s `connect_timeout` (`db.py:50`), well within 5 s. |
| AC-002.5 | met | `tests/test_task_persistence.py::test_ready_503_when_database_down_health_ok`, `::test_ready_200_when_database_up`; `tests/test_health.py::test_ready_returns_ready` | `src/taskboard7_api/main.py:46-51`; `src/taskboard7_api/db.py:88-103` (ping in a daemon thread with `join(1.0)`) | The tests assert the exact bodies `{"status": "not ready"}` and `{"status": "ready"}`, and `/health` answering 200 `{"status": "ok"}` while the database is down. `/health` is unchanged (`main.py:32-35`). |
| AC-002.6 | met | `tests/test_task_persistence.py::test_recovers_without_restart` | `src/taskboard7_api/db.py:43-55`, `:70-86` (a fresh connection per call, no cached failure); `:66` (schema flag set only after success); `src/taskboard7_api/db.py:110-116` and `tasks/store.py:49-55` (lazy singletons: nothing connects at import or startup) | The test shows `/ready` and `/tasks` returning 503, then 200 and 201 on the same app object without re-importing it. Caveat, same as before: recovery is simulated by swapping in a new `Database` instance, which design.md allows. Because the code keeps no connection state between calls, the same instance recovers too. |

## Non-goals

The spec lists no non-goals. Nothing outside the spec was added: no auth, no paging, no pool. The router and models are unchanged, as the spec requires. This is an API with no template-owned page layout. The `main.py` changes are limited to the 503 handler and `/ready`, which the spec asks for. `/health`, `/ping` and `/metrics` are unchanged.

## Deviations from the plan

- `tests/conftest.py` and `tests/test_task_persistence.py` are in no task's `files`. They are the acceptance-test commit (`923b2b5`), its fixtures, and the user-approved tightening in `f9c092a`. Acceptable.
- `docs/adr/001-postgres-with-psycopg.md`, `docs/backlog.md` and the spec, plan, design and verification files are in no task's `files`. They are spec and plan pipeline artefacts. Acceptable. `docs/backlog.md:11` still shows 002 as `approved` while the spec says `building`. The index is generated, so this fixes itself on the next `cplat spec index`.
- Tasks t1 to t3 are all `done: true`.

## Contract

The build matches `design.md` on:

- the interfaces: `Database`, `DatabaseUnavailableError`, `get_database`, `TaskRepository`, `PostgresTaskStore`, and the constants 2 / 3000 / 1.0 at `db.py:13-15`
- the schema, with an advisory lock during bootstrap
- the 503 body and content type
- `/ready` with no caching
- 422 staying FastAPI's default

Minor deviations, both acceptable:

- The `database_unavailable` log uses the `operation` values `connect`, `query` and `NotConfigured` instead of design.md's `add`, `list` and `ready`. No criterion depends on it, and neither the URL nor the title is logged.
- `tasks/router.py` still annotates `TaskStore` while it receives a `PostgresTaskStore`. This works at runtime, and the spec requires the router to stay unchanged.

No suppressions were found in the acceptance tests (`tests/test_task_persistence.py`, `tests/conftest.py`). The `noqa` marks at `db.py:97` and `main.py:47` are in source files, not in tests.

## Mutation check (report only)

13 of 20 mutants of the changed code were caught by the acceptance tests (65 %; spec 152, report only).

Survived (a test that names the criterion would fail if it checked this):
- `src/taskboard7_api/db.py:13 2 → 3`
- `src/taskboard7_api/db.py:14 3000 → 3001`
- `src/taskboard7_api/db.py:17 727002 → 727003`
- `src/taskboard7_api/db.py:116 return value → None`
- `src/taskboard7_api/db.py:114 Is → IsNot`
- `src/taskboard7_api/db.py:66 True → False`
- `src/taskboard7_api/tasks/store.py:55 return value → None`
