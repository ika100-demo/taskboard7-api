# Design — 001 Create and list tasks

## Decisions

- **A `tasks` subpackage with its own `APIRouter`**, included by `main.py`. Health, metrics and ping stay in `main.py` unchanged; task code does not leak into the entry point beyond one `include_router` call. This is the pattern later task features (update, delete) extend.
- **In-memory store behind a FastAPI dependency.** `TaskStore` is a small class holding an ordered list guarded by a `threading.Lock` (sync endpoints run in FastAPI's thread pool, so concurrent creates must not interleave). A module-level singleton is returned by `get_task_store()`, which the router takes via `Depends`. Swapping in persistence later means replacing the dependency, not the router. No ADR: the spec makes in-memory storage a deliberate, feature-local choice (non-goal: persistence).
- **Strict `due_date` parsing, not Pydantic's lax `date`.** Pydantic's lax `date` accepts `"2026-12-01T00:00:00"` and Unix timestamp integers, which AC-001.4 must reject. The request field is validated as: value is `None`, or a `str` that matches `^\d{4}-\d{2}-\d{2}$` and parses with `datetime.date.fromisoformat` (rejects `"2026-02-30"`). Anything else raises a validation error on `due_date` (AC-001.4, A3).
- **Strict `title`**: `StrictStr`, `min_length=1`, `max_length=200` (length in Python code points), plus a validator rejecting values with no non-whitespace character. Stored exactly as sent, no trimming (AC-001.3, A2).
- **Validation errors are FastAPI's standard 422 body** (A5). No custom exception handler.
- **`id` is `str(uuid.uuid4())`**, generated in the store (AC-001.1, AC-001.7, A7). Any client-supplied `id` is ignored like any other unknown field (A8).

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `src/taskboard7_api/tasks/__init__.py` | package marker, re-exports `router` | new |
| `src/taskboard7_api/tasks/models.py` | `TaskCreate` (request, validation), `Task` (response) | new |
| `src/taskboard7_api/tasks/store.py` | `TaskStore` (thread-safe ordered in-memory list), `get_task_store()` | new |
| `src/taskboard7_api/tasks/router.py` | `POST /tasks`, `GET /tasks` | new |
| `src/taskboard7_api/main.py` | `app.include_router(tasks.router)` | changed |

### Python interfaces (binding for tests and coders)

```python
# models.py
class TaskCreate(BaseModel):          # model_config: extra="ignore" (default)
    title: StrictStr                  # 1..200 chars, at least one non-whitespace char
    due_date: date | None = None      # input validated strictly as described above

class Task(BaseModel):
    id: str
    title: str
    due_date: date | None             # serialized as "YYYY-MM-DD" or null, never omitted

# store.py
class TaskStore:
    def add(self, title: str, due_date: date | None) -> Task: ...   # assigns uuid4 id, appends
    def list(self) -> list[Task]: ...                              # copy, insertion order
    def clear(self) -> None: ...                                   # test hook

def get_task_store() -> TaskStore: ...                             # returns the module singleton
```

**Test isolation:** the store lives for the process lifetime, so in-process tests share it. Tests get a fresh store per test with `app.dependency_overrides[get_task_store] = lambda: fresh_store` (or call `get_task_store().clear()` in a fixture). Import path: `taskboard7_api.tasks.store.get_task_store`.

## Contract

All bodies are `application/json`.

### `POST /tasks`

Request body:

| Field | Type | Required | Rules |
|---|---|---|---|
| `title` | string | yes | JSON string (no coercion from numbers/bools), 1–200 characters, at least one non-whitespace character; stored verbatim |
| `due_date` | string \| null | no | `YYYY-MM-DD`, a real calendar date; past dates allowed; absent or `null` → stored as `null` |
| any other field | – | – | ignored (A8), including `id` |

Responses:

- `201 Created` — body is the created task (AC-001.1, AC-001.2):
  ```json
  {"id": "3f1c…", "title": "Buy milk", "due_date": "2026-12-01"}
  ```
  `id`: non-empty opaque string, unique per task; clients must not parse it. `due_date`: `"YYYY-MM-DD"` or `null` (key always present). Exactly these three keys.
- `422 Unprocessable Entity` — FastAPI's standard validation body; no task is created (AC-001.3, AC-001.4):
  ```json
  {"detail": [{"type": "string_too_long", "loc": ["body", "title"], "msg": "…", "input": "…"}]}
  ```
  `detail` is a non-empty array; for an invalid `title` at least one entry has `loc == ["body", "title"]`, for an invalid `due_date` at least one entry has `loc == ["body", "due_date"]`. `type` and `msg` values are not part of the contract. A body that is not a JSON object also answers `422` (loc `["body"]`).

### `GET /tasks`

- `200 OK` — JSON array of all tasks in creation order, oldest first, no limit; each element has the same shape as the `201` body (AC-001.5, AC-001.7). `[]` when no task exists since startup (AC-001.6).

No other endpoints change. `/health`, `/ready`, `/ping`, `/metrics` are unaffected.

## Data

In-memory only: a `list[Task]` inside `TaskStore`, appended under a lock. Emptied on process restart; not shared between replicas (spec non-goal).

## Risks

- **Smoke test AC-001.6 against a deployed instance:** in dev, earlier smoke runs (AC-001.1, writing) leave tasks behind, so "empty array" only holds right after a restart. The read-only smoke check should assert `200` and a JSON array; the exact `[]` assertion belongs in the in-process acceptance test. Testers decide; flagged here so it is not a surprise.
- **Multiple replicas** would each show a different list. Acceptable per non-goals; the gitops entry should keep `replicas: 1` until persistence exists (no change needed if it already is).
- Unbounded memory growth: accepted for this in-memory stage (A6, no limit).
