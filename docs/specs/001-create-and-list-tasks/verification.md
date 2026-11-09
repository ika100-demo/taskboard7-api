# Verification — 001 Create and list tasks

**Result:** pass
**Commit:** 5d30338 · **Base:** f6659e9 · **Trace:** 7/7 criteria named by tests (smoke: AC-001.1, AC-001.6)

| Criterion | Verdict | Tests | Implementation | Notes |
|---|---|---|---|---|
| AC-001.1 | met | `tests/test_tasks.py::test_create_task_returns_201_with_fields`, `tests/test_smoke_tasks.py::test_smoke_ac_001_1_create_task` | `src/taskboard7_api/tasks/router.py:13-18`, `src/taskboard7_api/tasks/store.py:18` | Asserts 201, non-empty string `id`, title, due_date, and exactly three keys. Smoke test is marked `writes` and uses a `smoke-<uuid>` title. |
| AC-001.2 | met | `tests/test_tasks.py::test_create_task_without_due_date` (absent and `null`) | `src/taskboard7_api/tasks/models.py:16,28-29,43` | `Task.due_date` has no default, so the key is always serialized as `null`. |
| AC-001.3 | met | `tests/test_tasks.py::test_invalid_title_rejected` (missing, 123, true, "", "   ", 201 chars) | `src/taskboard7_api/tasks/models.py:15,18-23` | Each case asserts 422, `loc == ["body","title"]` and an empty list afterwards. `StrictStr` rejects number and bool input. No test for the 200-char upper bound being accepted (not required by the criterion). |
| AC-001.4 | met | `tests/test_tasks.py::test_invalid_due_date_rejected` ("tomorrow", "2026-02-30", "2026-12-01T10:00:00") | `src/taskboard7_api/tasks/models.py:9,25-35` | 422, `loc == ["body","due_date"]`, no task created. The regex plus `fromisoformat` also rejects ints and `T00:00:00`. |
| AC-001.5 | met | `tests/test_tasks.py::test_list_in_creation_order` | `src/taskboard7_api/tasks/router.py:21-24`, `src/taskboard7_api/tasks/store.py:23-25` | Checks 200, full equality with the creation responses (id, title, due_date) and the order A, B, C. |
| AC-001.6 | met | `tests/test_tasks.py::test_list_empty`, `tests/test_smoke_tasks.py::test_smoke_ac_001_6_list_tasks_is_json_array` | `src/taskboard7_api/tasks/router.py:21-24`, `src/taskboard7_api/tasks/store.py:13-14` | The in-process test asserts `[]` exactly. The smoke test only checks for a 200 JSON array, by design (design.md Risks: dev holds earlier smoke data). |
| AC-001.7 | met | `tests/test_tasks.py::test_duplicate_titles_get_distinct_ids` | `src/taskboard7_api/tasks/store.py:18` (`uuid4`) | Two tasks are listed and their ids differ. |

Observation (not a failure): every in-process test overrides `get_task_store` with a fresh `TaskStore`. The real singleton wiring (`store.py:32-36`) and `clear()` (`store.py:27-29`) are therefore not exercised in-process (these are the uncovered lines at 86% coverage). The smoke tests cover the wiring against a deployed instance.

## Non-goals

None of the excluded features are in the code: no persistence, no update/complete/delete endpoints, no filtering, paging or search, no auth, and no fields beyond `id`, `title`, `due_date` (`models.py:38-43`). ✔

Template-owned code: the only change to `main.py` is one import and one `include_router` call (`src/taskboard7_api/main.py:15,24`). Health, ready, ping and metrics are untouched. ✔

## Deviations from the plan

- `tests/test_tasks.py`, `tests/test_smoke_tasks.py` appear in no task's `files`. Acceptable: these are the acceptance tests from the red commit `8d73d5b`.
- `docs/specs/001-create-and-list-tasks/{spec,design,plan}.md` changed. Acceptable: the spec only moved to status `building` and gained a changelog line, and design and plan are new planning documents.
- `tasks/__init__.py` contains only a docstring, while the design.md module table says it "re-exports `router`". Acceptable: plan t1 explicitly says "no re-export", and `main.py` imports `tasks.router` directly.
- Both tasks t1 and t2 have `done: true`. ✔
- A third smoke test, `test_smoke_ac_001_1_rejects_invalid_input` (read-only 422 check), is extra to the one-per-criterion rule. Acceptable: it gives read-only environments a passing check for AC-001.1.

## Contract

The code matches `design.md`. `POST /tasks` returns 201 with exactly `id`, `title`, `due_date`. Invalid input gets FastAPI's standard 422 body (no custom handler), with `loc` naming the field. Unknown fields are ignored (default `extra`). `GET /tasks` returns 200 with an array in creation order and no limit. The store is guarded by a `threading.Lock` and reached through `Depends(get_task_store)`. Creation is logged with `task_id` only; the title is never logged (`router.py:17`). ✔

## Suppressions in acceptance tests

None. The only suppressions are `# noqa: B008` on the `Depends(...)` defaults in `src/taskboard7_api/tasks/router.py:14,22`, which is production code, not tests. That finding is a false positive: `Depends` in a default is the idiomatic FastAPI pattern.

## Mutation check (report only)

11 of 13 mutants of the changed code were caught by the acceptance tests (85 %; spec 152, report only).

Survived (a test that names the criterion would fail if it checked this):
- `src/taskboard7_api/tasks/models.py:30 and → or`
- `src/taskboard7_api/tasks/store.py:36 return value → None`
