from __future__ import annotations

from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from deepagents import create_deep_agent

from .prompts import (
    ANALYTICS_WORKER_SYSTEM,
    CONTENT_WORKER_SYSTEM,
    GENERAL_WORKER_SYSTEM,
    RESEARCH_WORKER_SYSTEM,
    SOCIAL_WORKER_SYSTEM,
)


def create_research_worker_agent(model: BaseChatModel, tools: List[BaseTool]):
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        system_prompt=RESEARCH_WORKER_SYSTEM,
    )


def create_content_worker_agent(model: BaseChatModel, tools: List[BaseTool]):
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        system_prompt=CONTENT_WORKER_SYSTEM,
    )


def create_analytics_worker_agent(model: BaseChatModel, tools: List[BaseTool]):
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        system_prompt=ANALYTICS_WORKER_SYSTEM,
    )


def create_social_worker_agent(model: BaseChatModel, tools: List[BaseTool]):
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        system_prompt=SOCIAL_WORKER_SYSTEM,
    )


def create_general_worker_agent(model: BaseChatModel):
    # General worker has NO external tools
    return create_deep_agent(
        model=model,
        tools=[],
        subagents=[],
        system_prompt=GENERAL_WORKER_SYSTEM,
    )
