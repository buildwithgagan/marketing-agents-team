from __future__ import annotations

from typing import List
import datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from deepagents import create_deep_agent

from .prompts import (
    ANALYTICS_WORKER_SYSTEM,
    CONTENT_WORKER_SYSTEM,
    GENERAL_WORKER_SYSTEM,
    RESEARCH_WORKER_SYSTEM,
    SOCIAL_WORKER_SYSTEM,
    REPORT_WORKER_SYSTEM,
    REVIEWER_WORKER_SYSTEM,
    STRATEGIST_WORKER_SYSTEM,
)


def _get_dated_prompt(prompt: str) -> str:
    now = datetime.datetime.now().strftime("%d %B %Y")
    return f"CURRENT DATE: {now}\n\n{prompt}"


def create_research_worker_agent(model: BaseChatModel, tools: List[BaseTool]):
    return create_deep_agent(
        model=model,
        # Research worker gets ALL tools (Tavily + Marketing)
        tools=tools,
        subagents=[],
        system_prompt=_get_dated_prompt(RESEARCH_WORKER_SYSTEM),
    )


def create_report_worker_agent(model: BaseChatModel):
    # Report worker focuses on writing, no tools needed (uses context)
    return create_deep_agent(
        model=model,
        tools=[],
        subagents=[],
        system_prompt=_get_dated_prompt(REPORT_WORKER_SYSTEM),
    )


def create_reviewer_agent(model: BaseChatModel):
    # Reviewer acts as a critic, no tools usually needed (uses internal knowledge)
    return create_deep_agent(
        model=model,
        tools=[],
        subagents=[],
        system_prompt=_get_dated_prompt(REVIEWER_WORKER_SYSTEM),
    )


def create_strategist_agent(model: BaseChatModel):
    return create_deep_agent(
        model=model,
        tools=[],
        subagents=[],
        system_prompt=_get_dated_prompt(STRATEGIST_WORKER_SYSTEM),
    )


def create_content_worker_agent(model: BaseChatModel, tools: List[BaseTool]):
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        system_prompt=_get_dated_prompt(CONTENT_WORKER_SYSTEM),
    )


def create_analytics_worker_agent(model: BaseChatModel, tools: List[BaseTool]):
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        system_prompt=_get_dated_prompt(ANALYTICS_WORKER_SYSTEM),
    )


def create_social_worker_agent(model: BaseChatModel, tools: List[BaseTool]):
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        system_prompt=_get_dated_prompt(SOCIAL_WORKER_SYSTEM),
    )


def create_general_worker_agent(model: BaseChatModel):
    # General worker has NO external tools
    return create_deep_agent(
        model=model,
        tools=[],
        subagents=[],
        system_prompt=_get_dated_prompt(GENERAL_WORKER_SYSTEM),
    )
