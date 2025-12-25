# Research Mode - Deep research with multi-agent coordination

from .graph import create_research_graph
from .prompts import RESEARCH_SYSTEM_PROMPT, DISCOVERY_AGENT_PROMPT, EXTRACTION_AGENT_PROMPT
from .subagents import create_subagent_configs

__all__ = [
    "create_research_graph",
    "RESEARCH_SYSTEM_PROMPT",
    "DISCOVERY_AGENT_PROMPT",
    "EXTRACTION_AGENT_PROMPT",
    "create_subagent_configs",
]

