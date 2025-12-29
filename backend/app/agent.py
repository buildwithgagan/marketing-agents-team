"""
Agent Manager - Central hub for managing all agent modes.

Modes:
- brew: Standard Chat Assistant (default)
- investigator: Dedicated Human-in-the-Loop research agent (managed via server)
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.runnables import ConfigurableField
from langgraph.checkpoint.memory import MemorySaver

# Load env variables
load_dotenv()

# Verify OPENAI_API_KEY is loaded
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY not found in environment variables. "
        "Please ensure it's set in your .env file or environment."
    )
print(f"✓ OPENAI_API_KEY loaded")


class AgentManager:
    """
    Manages multiple agent modes and their lifecycle.

    Attributes:
        agents: Dictionary of compiled graphs by mode name
        checkpointer: Memory checkpointer for conversation history
    """

    def __init__(self):
        self.agents = {}
        self.checkpointer = MemorySaver()
        self.model = None

    async def initialize(self):
        """Initialize all agents."""
        # === Configure Model ===
        self._configure_model()

        # === Initialize All Modes ===
        self._initialize_brew_mode()

        print("Agents initialized successfully (brew).")

    def _configure_model(self):
        """Configure the base model with dynamic overrides."""
        # Ensure API key is available
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found. Please check your .env file.")

        self.model = ChatOpenAI(
            model="gpt-4.1", temperature=0, api_key=api_key  # Explicitly pass API key
        ).configurable_fields(
            model_name=ConfigurableField(id="model_name"),
            reasoning=ConfigurableField(id="reasoning"),
            output_version=ConfigurableField(id="output_version"),
        )

    def _initialize_brew_mode(self):
        """Initialize Brew Mode - Standard Chat."""
        from .brew.graph import create_brew_graph

        brew_graph = create_brew_graph(model=self.model, checkpointer=self.checkpointer)
        self.agents["brew"] = brew_graph
        print("  [OK] Brew mode initialized")

    def get_agent(self, mode: str = None):
        """
        Get the agent for the specified mode.

        Args:
            mode: The mode to use. Options:
                - None or "brew": Standard Chat (default)

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
        # No cleanup needed currently
        pass


# Global agent manager instance
agent_manager = AgentManager()
