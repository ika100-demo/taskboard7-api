# ADR-001: Postgres via psycopg 3, plain SQL, schema bootstrapped on first connection

## Status

Accepted (spec 002-store-tasks-in-postgres-so-they-survive).

## Context

Tasks must survive restarts and be shared between instances (spec 002). The system's gitops repo provides a Postgres
resource and injects `DATABASE_URL`. The service must start while the database is unreachable (no crash loop), fail
fast with `503` while it is down, and recover without a restart. The data model is one small table; the handlers are
synchronous FastAPI endpoints.

## Decision

- **Driver:** `psycopg[binary]` 3 (sync API), plain parameterised SQL. No ORM: one table does not justify SQLAlchemy's
  weight, and plain SQL keeps the timeouts and error mapping explicit.
- **Connections:** one short-lived connection per database operation, opened with `connect_timeout=2` and
  `statement_timeout=3000` ms, closed after use. No connection pool for now: it keeps no background state that could
  hold a request on a dead database or delay recovery behind a reconnect backoff, and the request rate is low. The
  connection is created behind a single `Database.connection()` method, so a pool can replace it later without
  touching callers.
- **Schema:** no migration tool yet. On the first successful connection per process, the service runs an idempotent
  `CREATE TABLE IF NOT EXISTS` inside a transaction guarded by a transaction-scoped advisory lock, so concurrent
  instances do not race. A later schema change introduces a migration tool (new ADR).
- **Failure mapping:** every connection, timeout or operational driver error is raised as one domain exception,
  `DatabaseUnavailableError`, which the app turns into `503 {"detail": "Database unavailable"}`.
- **Tests:** a throw-away Postgres from `testcontainers[postgres]` (or an existing one given by `TEST_DATABASE_URL`).

## Consequences

**Positive:** deterministic fail-fast and recovery semantics; no new framework; easy to read and test.

**Negative:** a TCP + auth handshake per request (milliseconds in-cluster); revisit with a pool if latency or
connection count matters. Schema evolution beyond `CREATE TABLE IF NOT EXISTS` needs a migration tool. Running the
test suite needs Docker (or `TEST_DATABASE_URL`).
