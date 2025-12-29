import os
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.runnables import ConfigurableField
from dotenv import load_dotenv

from .state import BrewState
from .prompts import BREW_SYSTEM_PROMPT

# Load env variables
load_dotenv()


def create_brew_graph(
    model: ChatOpenAI = None, checkpointer: BaseCheckpointSaver = None
):
    """
    Creates the Brew (Chat) graph.
    Start -> Agent -> End
    """

    # If no model provided, create a default one (though usually passed from manager)
    if not model:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found. Please check your .env file.")
        model = ChatOpenAI(model="gpt-4.1", temperature=0, api_key=api_key)

    # Allow model parameters to be configured at runtime
    configured_model = model.configurable_fields(
        model_name=ConfigurableField(id="model_name"),
        reasoning=ConfigurableField(id="reasoning"),
        output_version=ConfigurableField(id="output_version"),
    )

    async def brew_agent(state: BrewState):
        messages = state["messages"]

        # Prepend system prompt if not present (simplistic check)
        # Ideally, we manage this more robustly or rely on the UI to send it,
        # but for a backend agent, we inject it here.

        # We'll rely on the model to handle the system message if we pass it as the first message
        # But to be safe and stateless regarding history, we can construct the call:

        system_msg = SystemMessage(content=BREW_SYSTEM_PROMPT)

        # We don't want to permanently add the system prompt to the user's conversation history
        # stored in the checkpoint if it duplicates.
        # For simplicity in this "chat" mode, we just invoke the model with the system prompt + messages.

        response = await configured_model.ainvoke([system_msg] + messages)
        return {"messages": [response]}

    builder = StateGraph(BrewState)
    builder.add_node("agent", brew_agent)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)

    return builder.compile(checkpointer=checkpointer)
