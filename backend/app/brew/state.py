from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


WorkerName = Literal["research", "content", "analytics", "social", "general"]


class TaskAssignment(BaseModel):
    worker: WorkerName = Field(description="Which worker should do this task.")
    task: str = Field(description="Clear, specific task for the worker to execute.")
    priority: int = Field(
        default=2, ge=1, le=3, description="1=highest priority, 3=lowest."
    )


class TaskPlan(BaseModel):
    reasoning: str = Field(
        default="",
        description="Short explanation of why these workers/tasks were chosen.",
    )
    tasks: list[TaskAssignment] = Field(default_factory=list)


class WorkerReport(BaseModel):
    worker: WorkerName
    task: str
    status: Literal["success", "partial", "failed"] = "success"
    result: str = ""
    sources: list[str] = Field(default_factory=list)


class BrewState(TypedDict, total=False):
    # Conversation
    messages: list

    # Planning / execution
    task_plan: TaskPlan
    worker_reports: Annotated[list[WorkerReport], operator.add]
    next_task_index: int

    # Output
    final_response: str
    status: str


class WorkerState(TypedDict, total=False):
    assignment: TaskAssignment
    worker_reports: Annotated[list[WorkerReport], operator.add]
    next_task_index: int
