"""HTTP routes for tasks."""

import structlog
from fastapi import APIRouter, Depends

from taskboard7_api.tasks.models import Task, TaskCreate
from taskboard7_api.tasks.store import TaskStore, get_task_store

router = APIRouter(tags=["tasks"])
logger = structlog.get_logger(__name__)


@router.post("/tasks", response_model=Task, status_code=201)
def create_task(body: TaskCreate, store: TaskStore = Depends(get_task_store)) -> Task:  # noqa: B008
    """Create a task."""
    task = store.add(body.title, body.due_date)
    logger.info("task_created", task_id=task.id)
    return task


@router.get("/tasks", response_model=list[Task])
def list_tasks(store: TaskStore = Depends(get_task_store)) -> list[Task]:  # noqa: B008
    """List all tasks, oldest first."""
    return store.list()
