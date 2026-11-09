"""FastAPI entry point for taskboard7-api."""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import __version__
from .db import Database, DatabaseUnavailableError, get_database
from .logging_config import configure_logging
from .metrics import MetricsMiddleware
from .tasks.router import router as tasks_router
from .tracing import configure_tracing, tracing_enabled

configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
if tracing_enabled():
    configure_tracing()

app = FastAPI(title="taskboard7-api", version=__version__)
app.add_middleware(MetricsMiddleware)
app.include_router(tasks_router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — returns 200 as long as the process is responding."""
    return HealthResponse(status="ok")


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(
    request: Request, exc: DatabaseUnavailableError
) -> JSONResponse:
    """Map a database outage to 503."""
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.get("/ready", response_model=HealthResponse)
def ready(database: Database = Depends(get_database)) -> HealthResponse | JSONResponse:  # noqa: B008
    """Readiness probe — 200 only while the database answers SELECT 1."""
    if database.ping():
        return HealthResponse(status="ready")
    return JSONResponse(status_code=503, content={"status": "not ready"})


@app.get("/ping")
def ping() -> dict[str, str]:
    """Simple ping endpoint."""
    return {"pong": "taskboard7-api"}


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
