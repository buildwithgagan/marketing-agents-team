"""
Research Mode Graph - Deep research with multi-agent coordination.

Uses the deepagents library to create a master agent with specialized
subagents for discovery and extraction.
"""

from typing import List
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from .prompts import RESEARCH_SYSTEM_PROMPT
from .subagents import create_subagent_configs


def create_research_graph(
    model: BaseChatModel,
    tools: List[BaseTool],
    checkpointer: MemorySaver = None,
):
    """
    Create the Research Mode graph using deepagents.

    Architecture:
    ```
    START
      │
      ▼
    [Master Deep Agent]
      │
      ├─────────────────┐
      ▼                 ▼
    [Discovery Agent] [Extraction Agent]
      │                 │
      └────────┬────────┘
               │
               ▼
    [Master Synthesis]
               │
               ▼
             END
    ```

    The master agent orchestrates:
    1. Planning phase - creates a research plan
    2. Discovery phase - finds relevant sources
    3. Extraction phase - gets full content
    4. Synthesis phase - combines findings

    Args:
        model: The language model to use
        tools: List of tools (Tavily search/extract)
        checkpointer: Optional memory checkpointer

    Returns:
        Compiled deep agent graph
    """
    from deepagents import create_deep_agent

    # Create subagent configurations
    subagents = create_subagent_configs(model, tools)

    # Create the deep agent with subagents
    research_graph = create_deep_agent(
        model=model,
        tools=tools,
        subagents=subagents,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )

    return research_graph


def create_research_graph_simple(
    model: BaseChatModel,
    tools: List[BaseTool],
    checkpointer: MemorySaver = None,
):
    """
    Create a simpler Research Mode graph without subagents.

    For faster research when full multi-agent coordination isn't needed.
    Still follows the research protocol but uses a single agent.

    Args:
        model: The language model to use
        tools: List of tools (Tavily search/extract)
        checkpointer: Optional memory checkpointer

    Returns:
        Compiled deep agent graph (single agent mode)
    """
    from deepagents import create_deep_agent

    # Create without subagents for faster execution
    research_graph = create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],  # No subagents
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )

    return research_graph

