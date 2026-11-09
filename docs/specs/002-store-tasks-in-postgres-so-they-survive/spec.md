---
spec_id: 002-store-tasks-in-postgres-so-they-survive
title: Store tasks in Postgres so they survive restarts and are shared between instances
status: building
priority: P1
shape: service-python
parent: ika100-demo/taskboard7-gitops:001-persistent-tasks-in-postgres-with-web-ui
---

# 002 — Store tasks in Postgres so they survive restarts and are shared between instances

## Problem

The taskboard7 Task API can create and list tasks, but keeps them in memory: every restart or redeploy empties the board, and two instances of the API would each show a different list. People also have no way to use the board except by calling the API by hand, because the web front end has no task features yet. Keeping tasks in a Postgres database and giving the web app a task page turns the board into something people can actually rely on and use.

## System context

Slice of the system plan `001-persistent-tasks-in-postgres-with-web-ui` in `ika100-demo/taskboard7-gitops` for `taskboard7-api` (service-python). The system criteria and the contract below are binding: every criterion of this spec implements one of them and names it: `(system AC-<NNN>.<n>)`.

### System criteria

- **AC-001.1** Given tasks A, B and C were created through the Task API, when the Task API is restarted or redeployed and a client then sends `GET /tasks`, then the response is `200` with exactly A, B and C, oldest first, each with the same `id`, `title` and `due_date` as returned on creation.
- **AC-001.2** Given the Task API runs with two instances, when a task is created through one instance, then a `GET /tasks` answered by the other instance contains that task.
- **AC-001.3** Given the database, when clients use `POST /tasks` and `GET /tasks`, then requests, response fields, status codes and validation errors are the same as in the Task API's component spec 001 (create and list tasks): its criteria AC-001.1 to AC-001.7 still hold, except that tasks are no longer lost on restart.
- **AC-001.4** Given the database is unreachable, when a client sends `POST /tasks` or `GET /tasks`, then the response is `503` with a JSON error body and no task is created; the Task API's `/ready` answers not ready while the database is unreachable; and once the database is reachable again, both requests succeed without restarting the Task API.

### Contract

Caller: the taskboard7-web **server** (never the browser). Callee: taskboard7-api at `API_URL` (cluster:
`http://taskboard7-api`). JSON over HTTP, `Content-Type: application/json`, UTF-8. No authentication (non-goal).
Unchanged from the Task API's component spec 001; no version prefix.

**Task** object: `{"id": string, "title": string, "due_date": "YYYY-MM-DD" | null}`. `id` is an opaque, non-empty,
server-generated string (today a uuid4); clients must not parse it. `due_date` is always present, `null` when unset.

`POST /tasks`
- Request: `{"title": string, "due_date": "YYYY-MM-DD" | null}`; `due_date` may be omitted (= null). Unknown fields
  are ignored.
- `title`: a string of 1 to 200 characters (Unicode code points) with at least one non-whitespace character, stored
  exactly as sent (no trimming). `due_date`: a calendar date `YYYY-MM-DD`, no time, past dates allowed.
- `201`: the created Task.
- `422`: invalid input, FastAPI's standard shape `{"detail": [{"loc": ["body", "<field>"], "msg": ..., "type": ...}]}`
  naming `title` or `due_date`. Validation runs before any database access, so invalid input answers 422 even when
  the database is down. Nothing is stored.
- `503`: the database is unreachable or too slow: `{"detail": "Database unavailable"}`. Nothing is stored.

`GET /tasks`
- `200`: a JSON array of all Tasks, oldest first (creation order), no paging; `[]` when there are none.
- `503`: `{"detail": "Database unavailable"}`.

`GET /ready` (platform probe, not called by the web app)
- `200 {"status": "ready"}` when a `SELECT 1` on the database succeeds within 1 s; otherwise
  `503 {"status": "not ready"}`. `GET /health` stays `200 {"status": "ok"}` regardless of the database.

No events.

### Errors

- The Task API's error bodies are JSON with a `detail` field: a list of validation items for `422`, a string for
  `503` (and for any other framework error such as `404`/`405`/`500`).
- The web app treats exactly two responses as success: `200` with a JSON array for `GET /tasks`, `201` with a Task
  object for `POST /tasks`. Every other outcome — any other status (`422`, `503`, `5xx`, `4xx`), a body that is not
  the expected JSON, a connection error or a timeout — is a failure: the page shows "Tasks could not be loaded. Try
  again later." (list) or "The task could not be saved. Try again." (create, values kept). The web app never shows
  the API's `detail` text and never retries a `POST`.
- The web app logs the failure (status or error kind) server-side as structured JSON, without the task title.

### Timeouts

- web -> `GET /tasks`: 5 s total per request, no retry; on timeout the list error message is shown.
- web -> `POST /tasks`: 5 s total per request, no retry (a retry could create a duplicate task); on timeout the save
  error message is shown. A create that timed out on the web side may still have been stored; it shows up on the next
  page load.
- Task API -> Postgres: connect timeout 2 s, statement timeout 3 s, so the API answers `503` within 5 s and before the
  web app gives up; `/ready` checks with a 1 s timeout. The API keeps no request waiting on a dead database: each
  request tries a (pooled) connection and fails fast; it reconnects by itself on the next request once the database is
  back.
- Database down: the Task API stays up (`/health` 200), reports not ready (Kubernetes removes it from the Service),
  and the web app shows the AC-001.8 messages. The web app's own `/api/ready` does not depend on the Task API.

### Provided by the system

The gitops part of this plan wires these for this repo; rely on them, do not ask for them again:

- resource `postgres`: env `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

### Notes for this repo

Connection: read DATABASE_URL (postgresql://...), injected by the gitops `uses: postgres`; the PG* variables are
also set. Locally and in tests use a throw-away Postgres (testcontainers or the devbox service). The process must
start even when the database is unreachable (no crash loop): connect lazily, create the schema (or run the
migration) on first successful connection, and reconnect on the next request.
Storage: one table `tasks` (id text primary key holding a uuid4 string, title text not null, due_date date null,
seq bigint generated always as identity) ordered by seq for "oldest first"; tasks in memory are not carried over.
Replace the in-memory TaskStore behind get_task_store, keep the router and models unchanged.
Database timeouts: connect 2 s, statement 3 s, /ready check (SELECT 1) 1 s; never retry a POST insert.

## Stories

<!-- As a <persona>, I want <goal>, so that <benefit>. -->

## Acceptance criteria

- **AC-002.1** Given tasks A, B and C were created with POST /tasks, when the Task API process is stopped and started again against the same database and a client sends GET /tasks, then the response is 200 with exactly A, B and C, oldest first, each with the same id, title and due_date as returned on creation (system AC-001.1)
- **AC-002.2** Given two Task API processes connected to the same database, when a task is created with POST /tasks on one of them, then GET /tasks on the other returns that task with the same id, title and due_date (system AC-001.2)
- **AC-002.3** Given the database, when clients use POST /tasks and GET /tasks, then every criterion of component spec 001 (AC-001.1 to AC-001.7) still holds unchanged: 201 with id, title and due_date (null when absent); 422 in FastAPI's standard validation shape naming title or due_date, with no task stored; GET /tasks returns all tasks oldest first, [] for an empty database; equal titles get different ids (system AC-001.3)
- **AC-002.4** Given the database is unreachable, when a client sends a valid POST /tasks or a GET /tasks, then the response is 503 with the JSON body {"detail": "Database unavailable"} within 5 seconds, and once the database is back no task from that POST exists (system AC-001.4)
- **AC-002.5** Given the database is unreachable, when the platform calls GET /ready, then it answers 503 with {"status": "not ready"} while GET /health keeps answering 200; given the database is reachable, GET /ready answers 200 with {"status": "ready"} (system AC-001.4)
- **AC-002.6** Given the Task API was started or kept running while the database was unreachable, when the database becomes reachable again, then GET /ready, POST /tasks and GET /tasks succeed without restarting the Task API (system AC-001.4)

## Non-goals

## Assumptions

<!-- Spec 149: decisions taken by default, approved with the spec. One bullet each: - **A1** <the decision> (other option: <…>; affects AC-…). A revised one is struck through (~~…~~), never deleted. -->

## Open questions

<!-- Only what may not be decided by default (spec 149): security or access, money, destroying or migrating data, or a request too ambiguous to build. Approval is refused while any is open. Strike answered ones (~~…~~) and fold the answer into the criteria. -->

## Changelog

- 2026-11-09 created from the system plan, with its criteria (spec 147)
- 2026-11-09 approved
- 2026-11-09 building
