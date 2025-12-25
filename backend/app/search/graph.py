"""
Search Mode Graph - Fast, single-agent search using LangGraph.

Optimized for quick answers to everyday questions.
Uses a simple ReAct loop without multi-agent coordination.
"""

from typing import List
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_core.messages import SystemMessage, ToolMessage

from .prompts import SEARCH_SYSTEM_PROMPT


def create_search_graph(
    model: BaseChatModel,
    tools: List[BaseTool],
    checkpointer: MemorySaver = None,
):
    """
    Create the Search Mode graph.

    Architecture:
    ```
    START
      │
      ▼
    [Agent] ◄──────┐
      │            │
      ▼            │
    [Should Continue?]
      │            │
      ├─ tools ────┤
      │            │
      ▼            │
    [Tool Executor]─┘
      │
      ▼
    END
    ```

    Args:
        model: The language model to use
        tools: List of tools (Tavily search/extract)
        checkpointer: Optional memory checkpointer

    Returns:
        Compiled StateGraph
    """

    async def search_agent(state: MessagesState) -> dict:
        """Main search agent node - calls the LLM with tools bound."""
        messages = state["messages"]

        # Prepend system prompt
        full_messages = [
            SystemMessage(content=SEARCH_SYSTEM_PROMPT),
            *messages,
        ]

        # Bind tools and invoke
        model_with_tools = model.bind_tools(tools)
        response = await model_with_tools.ainvoke(full_messages)

        return {"messages": [response]}

    async def tool_executor(state: MessagesState) -> dict:
        """Execute tool calls from the last message."""
        last_message = state["messages"][-1]
        tool_messages = []

        for tool_call in last_message.tool_calls:
            # Find the matching tool
            tool_result = f"Tool {tool_call['name']} not found"

            for tool in tools:
                if tool.name == tool_call["name"]:
                    try:
                        result = await tool.ainvoke(tool_call["args"])
                        tool_result = str(result)
                    except Exception as e:
                        tool_result = f"Error executing {tool_call['name']}: {str(e)}"
                    break

            tool_messages.append(
                ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call["id"],
                )
            )

        return {"messages": tool_messages}

    def should_continue(state: MessagesState) -> str:
        """Determine if we should continue with tool execution or end."""
        last_message = state["messages"][-1]

        # If there are tool calls, continue to tool execution
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        # Otherwise, we're done
        return "end"

    # Build the graph
    builder = StateGraph(MessagesState)

    # Add nodes
    builder.add_node("agent", search_agent)
    builder.add_node("tools", tool_executor)

    # Add edges
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "agent")

    # Compile
    if checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
    else:
        graph = builder.compile()

    return graph

