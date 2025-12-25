"""
Subagent configurations for Research Mode.

These are used by the deepagents library to create specialized
worker agents that assist the master researcher.
"""

from typing import List, Dict, Any
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from .prompts import DISCOVERY_AGENT_PROMPT, EXTRACTION_AGENT_PROMPT


def create_subagent_configs(
    model: BaseChatModel,
    tools: List[BaseTool],
) -> List[Dict[str, Any]]:
    """
    Create subagent configurations for the research mode.

    Args:
        model: The language model to use for subagents
        tools: List of tools (Tavily search/extract)

    Returns:
        List of subagent configuration dictionaries
    """
    discovery_agent = {
        "name": "research-agent",
        "description": "Expert in global discovery. Use this to find the best URLs and initial facts across the web.",
        "model": model,
        "tools": tools,
        "system_prompt": DISCOVERY_AGENT_PROMPT,
    }

    extraction_agent = {
        "name": "crawl-agent",
        "description": "Expert in deep extraction. Use this to scrape full text, technical docs, and structured data from specific URLs.",
        "model": model,
        "tools": tools,
        "system_prompt": EXTRACTION_AGENT_PROMPT,
    }

    return [discovery_agent, extraction_agent]
