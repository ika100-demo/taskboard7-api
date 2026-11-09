---
spec_id: 001-create-and-list-tasks
title: Create and list tasks
status: building
priority: P1
shape: service-python
---

# 001 — Create and list tasks

## Problem

The taskboard7 system has no way to record work yet: the Task API exposes only health endpoints, so clients of the system (such as its web front end) have nothing to create or show. A first, minimal task model (a title and an optional due date) lets clients start capturing and displaying tasks now. Storage is kept in memory on purpose so the API contract can be exercised before any persistence is chosen.

## Stories

As a client of the Task API, I want to create a task with a title and, if I like, a due date, so that the work is recorded on the board.

As a client of the Task API, I want to list all tasks, so that I can show the board's current contents.

## Acceptance criteria

- **AC-001.1** Given a running service, when a client sends `POST /tasks` with JSON `{"title": "Buy milk", "due_date": "2026-12-01"}`, then the response is `201` with a JSON body containing a server-assigned non-empty string `id`, `"title": "Buy milk"` and `"due_date": "2026-12-01"`. (smoke)
- **AC-001.2** Given a running service, when a client sends `POST /tasks` with JSON `{"title": "Buy milk"}` (no `due_date`), or with `"due_date": null`, then the response is `201` and the body has `"due_date": null`.
- **AC-001.3** Given a running service, when a client sends `POST /tasks` with `title` missing, not a string, empty, only whitespace, or longer than 200 characters, then the response is `422` with an error naming the `title` field, and a following `GET /tasks` does not contain a new task.
- **AC-001.4** Given a running service, when a client sends `POST /tasks` with a `due_date` that is not a calendar date in `YYYY-MM-DD` form (for example `"tomorrow"`, `"2026-02-30"` or `"2026-12-01T10:00:00"`), then the response is `422` with an error naming the `due_date` field, and no task is created.
- **AC-001.5** Given tasks were created in the order A, B, C, when a client sends `GET /tasks`, then the response is `200` with a JSON array of exactly those three tasks, oldest first, each with the same `id`, `title` and `due_date` as returned on creation.
- **AC-001.6** Given no task has been created since the service started, when a client sends `GET /tasks`, then the response is `200` with an empty JSON array `[]`. (smoke)
- **AC-001.7** Given two tasks created with the same title, when they are listed, then both appear with different `id` values.

## Non-goals

- Keeping tasks across a service restart or sharing them between replicas (tasks are in memory; a restart empties the list).
- Updating, completing or deleting tasks.
- Filtering, sorting options, paging or search on the list.
- Users, ownership, authentication or authorisation.
- Any field besides `id`, `title` and `due_date` (description, status, priority, timestamps).

## Assumptions

- **A1** The API paths are `POST /tasks` and `GET /tasks`, with JSON fields `id`, `title`, `due_date` (other option: a versioned prefix such as `/v1/tasks`; affects AC-001.1 to AC-001.7).
- **A2** A title is 1 to 200 characters and must contain at least one non-whitespace character; it is stored exactly as sent, without trimming (other option: trim surrounding whitespace before storing; affects AC-001.1, AC-001.3).
- **A3** `due_date` is a calendar date `YYYY-MM-DD` without time or time zone, and dates in the past are accepted (other option: a full timestamp, or rejecting past dates; affects AC-001.1, AC-001.4).
- **A4** An absent `due_date` is returned as `null`, not omitted (other option: leave the field out; affects AC-001.2).
- **A5** Invalid input answers `422` in the framework's standard validation error shape, naming the offending field (other option: `400` with a custom error body; affects AC-001.3, AC-001.4).
- **A6** The list returns all tasks, oldest first, with no limit (other option: newest first, or a page size cap; affects AC-001.5).
- **A7** The `id` is an opaque server-generated unique string; clients cannot choose it and must not rely on its format (other option: an incrementing integer; affects AC-001.1, AC-001.7).
- **A8** Unknown extra fields in the create request are ignored (other option: reject them with `422`; affects AC-001.1).

## Open questions

## Changelog

- 2026-11-09 created
- 2026-11-09 approved
- 2026-11-09 building
