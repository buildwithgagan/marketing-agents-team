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
        # self._initialize_omniscient_mode()
        self._initialize_investigator_mode()

        print("Agents initialized successfully (brew, investigator).")

    def _configure_model(self):
        """Configure the base model with dynamic overrides."""
        # Ensure API key is available
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found. Please check your .env file.")

        self.model = ChatOpenAI(
            model="gpt-5-mini", api_key=api_key  # Explicitly pass API key
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

    # def _initialize_omniscient_mode(self):
    #     """Initialize Omniscient Mode - Deep Report."""
    #     from .omniscient.graph import create_omniscient_graph
        
    #     # Omniscient uses its own checkpointer or shared memory? 
    #     # Using shared memory allows thread persistence in same DB
    #     omni_graph = create_omniscient_graph(checkpointer=self.checkpointer)
    #     self.agents["omniscient"] = omni_graph
    #     print("  [OK] Omniscient mode initialized")

    def _initialize_investigator_mode(self):
        """Initialize Investigator Mode - Strategic Research."""
        from .investigator.graph import build_investigator_graph
        
        # Investigator uses the shared checkpointer
        invest_graph = build_investigator_graph(checkpointer=self.checkpointer)
        self.agents["investigator"] = invest_graph
        print("  [OK] Investigator mode initialized")

    def get_agent(self, mode: str = None):
        """
        Get the agent for the specified mode.

        Args:
            mode: The mode to use. Options:
                - None or "brew": Standard Chat (default)
                - "omniscient": Deep Report Generator (not implemented)
                - "investigator": Strategic Research Agent

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
