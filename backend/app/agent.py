"""
Agent Manager - Central hub for managing all agent modes.

Modes:
- brew: Multi-agent orchestration with master + worker agents (default)
- search: Fast, single-agent search for quick answers
- research: Deep research with multi-agent coordination
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.runnables import ConfigurableField
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import MemorySaver

# Load env variables
load_dotenv()


class AgentManager:
    """
    Manages multiple agent modes and their lifecycle.

    Attributes:
        agents: Dictionary of compiled graphs by mode name
        tools: List of available tools (Tavily)
        checkpointer: Memory checkpointer for conversation history
    """

    def __init__(self):
        self.client = None
        self.session_context = None
        self.session = None
        self.agents = {}
        self.checkpointer = MemorySaver()
        self.tools = []
        self.model = None

    async def initialize(self):
        """Initialize all agents and tools."""
        # === Load Tools ===
        await self._initialize_tools()

        # === Configure Model ===
        self._configure_model()

        # === Initialize All Modes ===
        self._initialize_brew_mode()
        self._initialize_search_mode()
        self._initialize_research_mode()

        print("Agents initialized successfully for all modes (brew, search, research).")

    async def _initialize_tools(self):
        """Initialize Tavily MCP tools."""
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise ValueError("TAVILY_API_KEY not found in environment.")

        mcp_url = f"https://mcp.tavily.com/mcp?tavilyApiKey={tavily_api_key}"
        print("Connecting to Tavily MCP via 'npx mcp-remote' bridge...")

        self.client = MultiServerMCPClient(
            {
                "tavily": {
                    "command": "npx",
                    "args": ["-y", "mcp-remote", mcp_url],
                    "transport": "stdio",
                }
            }
        )

        self.session_context = self.client.session("tavily")
        self.session = await self.session_context.__aenter__()

        print("Session established. Loading tools...")
        self.tools = await load_mcp_tools(self.session)
        print(
            f"Loaded {len(self.tools)} tools from Tavily: {[t.name for t in self.tools]}"
        )

    def _configure_model(self):
        """Configure the base model with dynamic overrides."""
        self.model = ChatOpenAI(model="gpt-4.1", temperature=0).configurable_fields(
            model_name=ConfigurableField(id="model_name"),
            reasoning=ConfigurableField(id="reasoning"),
            output_version=ConfigurableField(id="output_version"),
            reasoning_effort=ConfigurableField(id="reasoning_effort"),
        )

    def _initialize_brew_mode(self):
        """Initialize Brew Mode - Multi-agent orchestration."""
        from .brew import create_brew_graph

        # Full brew graph (orchestrator-worker pattern)
        # Uses master agent to delegate to specialized workers
        brew_graph = create_brew_graph(
            model=self.model,
            tools=self.tools,
            checkpointer=self.checkpointer,
        )
        self.agents["brew"] = brew_graph

        print("  [OK] Brew mode initialized (multi-agent orchestration)")

    def _initialize_search_mode(self):
        """Initialize Search Mode - Fast, single-agent search."""
        from .search import create_search_graph

        search_graph = create_search_graph(
            model=self.model,
            tools=self.tools,
            checkpointer=self.checkpointer,
        )
        self.agents["search"] = search_graph

        print("  [OK] Search mode initialized")

    def _initialize_research_mode(self):
        """Initialize Research Mode - Deep research with subagents."""
        from .research import create_research_graph

        research_graph = create_research_graph(
            model=self.model,
            tools=self.tools,
            checkpointer=self.checkpointer,
        )
        self.agents["research"] = research_graph

        print("  [OK] Research mode initialized")

    def get_agent(self, mode: str = None):
        """
        Get the agent for the specified mode.

        Args:
            mode: The mode to use. Options:
                - None or "brew": Multi-agent orchestration (default)
                - "search": Fast single-agent search
                - "research": Deep research with subagents

        Returns:
            Compiled graph for the requested mode

        Raises:
            RuntimeError: If agents not initialized
        """
        # Default to brew mode if mode is None or empty
        if not mode:
            mode = "brew"

        # Normalize mode name
        mode = mode.lower().strip()

        if mode not in self.agents:
            # Fallback to brew if mode not found
            if "brew" in self.agents:
                print(f"Mode '{mode}' not found, falling back to 'brew'")
                return self.agents["brew"]
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        return self.agents[mode]

    def list_modes(self) -> list:
        """List all available modes."""
        return list(self.agents.keys())

    async def cleanup(self):
        """Cleanup resources."""
        if self.session_context:
            await self.session_context.__aexit__(None, None, None)
            print("MCP session closed.")


# Global agent manager instance
agent_manager = AgentManager()
