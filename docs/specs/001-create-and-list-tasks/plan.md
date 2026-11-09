---
spec_id: 001-create-and-list-tasks
shape: service-python
spec_hash: 2e28fcd7082c
summary: In-memory task model with POST /tasks (validated create) and GET /tasks (list, oldest first)
tasks:
  - id: t1
    title: Add task models and thread-safe in-memory TaskStore
    files: [src/taskboard7_api/tasks/__init__.py, src/taskboard7_api/tasks/models.py, src/taskboard7_api/tasks/store.py]
    covers: [AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7]
    parallel_safe: true
    depends_on: []
  - id: t2
    title: Add tasks router (POST/GET /tasks) and include it in the app
    files: [src/taskboard7_api/tasks/router.py, src/taskboard7_api/main.py]
    covers: [AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7]
    parallel_safe: false
    depends_on: [t1]
---

# Plan — 001 Create and list tasks

Contract, interfaces and validation rules: [design.md](design.md). Two serial tasks: the router imports what t1 creates.

## t1 — Add task models and thread-safe in-memory TaskStore

**Files:** src/taskboard7_api/tasks/__init__.py, src/taskboard7_api/tasks/models.py, src/taskboard7_api/tasks/store.py
**Covers:** AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7
**Goal:** Provide the request/response models with the spec's validation rules and the in-memory store that assigns ids and keeps creation order, exactly as the interfaces in design.md describe.

**Implementation notes:**
- `__init__.py`: package docstring only (no re-export; `main.py` imports `taskboard7_api.tasks.router` directly).
- `TaskCreate.title`: `StrictStr` with `min_length=1`, `max_length=200`, plus a `field_validator` raising `ValueError` when `not value.strip()`. Never trim the stored value (A2).
- `TaskCreate.due_date`: a `mode="before"` validator that accepts `None`, or a `str` matching `^\d{4}-\d{2}-\d{2}$` that `date.fromisoformat` parses; anything else (ints, datetimes like `2026-12-01T10:00:00` or `...T00:00:00`, `2026-02-30`, `"tomorrow"`) raises `ValueError` so the error `loc` is `due_date`. Absent defaults to `None`.
- Unknown fields ignored (Pydantic default `extra="ignore"`); do not set `forbid`.
- `Task`: `id: str`, `title: str`, `due_date: date | None` (no default: the key is always serialized, as `null` when unset).
- `TaskStore`: list + `threading.Lock`; `add()` builds `Task(id=str(uuid.uuid4()), ...)` and appends under the lock; `list()` returns a copy under the lock; `clear()` empties it.
- `get_task_store()` returns one module-level `TaskStore` instance.
- Full type hints (mypy strict); structlog not needed here.

**Done when:** unit-level checks pass: validation rejects each AC-001.3/AC-001.4 example and accepts the AC-001.1/AC-001.2 inputs; the store returns tasks in insertion order with distinct ids. `devbox run quality` is green. (The HTTP acceptance tests pass only after t2.)

## t2 — Add tasks router (POST/GET /tasks) and include it in the app

**Files:** src/taskboard7_api/tasks/router.py, src/taskboard7_api/main.py
**Covers:** AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7
**Goal:** Expose the contract in design.md: `POST /tasks` returns `201` with the created task, invalid input answers FastAPI's standard `422`, `GET /tasks` returns all tasks oldest first.

**Implementation notes:**
- `router = APIRouter(tags=["tasks"])`; sync handlers taking `store: TaskStore = Depends(get_task_store)` (tests override this dependency for isolation).
- `@router.post("/tasks", response_model=Task, status_code=201)` taking `TaskCreate`; calls `store.add(body.title, body.due_date)`. Validation happens before the handler runs, so a 422 never touches the store.
- `@router.get("/tasks", response_model=list[Task])` returns `store.list()`.
- Do not add a custom validation exception handler (A5).
- Log task creation with structlog (`task_created`, `task_id`), never the title.
- `main.py`: `from .tasks.router import router as tasks_router` and `app.include_router(tasks_router)` after the middleware; leave health, ready, ping and metrics untouched.

**Done when:** all acceptance tests for AC-001.1 to AC-001.7 pass, existing health/metrics tests still pass, and `devbox run ci` is green.
