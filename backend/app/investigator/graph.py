import json
import logging
import os
from typing import List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import ConfigurableField
from dotenv import load_dotenv

# Load env variables
load_dotenv()
from app.tools.marketing import (
    get_autocomplete_suggestions,
    get_google_trends,
    tavily_search,
    scrape_competitor_page,
)
from .state import AgentState
from .prompts import (
    get_current_date,
    PLANNER_SYSTEM_PROMPT,
    EXECUTOR_SYSTEM_PROMPT_TEMPLATE,
    REPORTER_SYSTEM_PROMPT_TEMPLATE,
)

# Setup Logger
logger = logging.getLogger(__name__)

# --- Models ---
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found. Please check your .env file.")

# Base model definition.
# NOTE: The actual model used is determined by the 'configurable' dict passed from server.py.
# 'gpt-4o' is just a fallback default if no config is provided.
base_llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)

llm = base_llm.configurable_fields(
    model_name=ConfigurableField(id="model_name"),
    reasoning=ConfigurableField(id="reasoning"),
    output_version=ConfigurableField(id="output_version"),
)

# --- Tools List ---
tools = [
    tavily_search,
    scrape_competitor_page,
    get_google_trends,
    get_autocomplete_suggestions,
]
llm_with_tools = llm.bind_tools(tools)


# --- Helper Functions ---


def extract_content_string(content: Any) -> str:
    """
    Extract string content from response.content which can be:
    - A string (legacy API)
    - A list of content blocks (responses API v1)
    - Other types (fallback to str())
    """
    if isinstance(content, list):
        content_str = ""
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                content_str += item.get("text", "")
            elif isinstance(item, str):
                content_str += item
        return content_str
    elif isinstance(content, str):
        return content
    else:
        return str(content)


# --- Nodes ---


async def planner_node(state: AgentState):
    """
    Generates a research plan based on the topic and user feedback.
    Performs an internal search step to identify concrete Competitor URLs.
    """
    topic = state.get("topic")
    user_feedback = state.get("user_feedback", "")

    logger.info(f"Planner Node: Generating plan for topic: {topic}")

    context = f"Topic: {topic}"
    if user_feedback:
        context += f"\n\nUser Feedback on previous plan: {user_feedback}"

    # --- INTERNAL STEP: Scout for Competitors/URLs ---
    # We do this here so the plan can have concrete URLs for the scraper.
    scout_query = f"top 5 companies for {topic} and their official website urls"
    logger.info(f"Planner Scouting: {scout_query}")

    try:
        # We invoke the tool directly.
        # Note: Depending on your tool implementation, this returns a string or list.
        # We handle both to be safe.
        search_result = tavily_search.invoke({"query": scout_query})

        scout_context = ""
        if isinstance(search_result, list):
            # If tool returns list of dicts
            for res in search_result:
                scout_context += f"- {res.get('title', 'Unknown')}: {res.get('url', 'No URL')} ({res.get('content', '')[:100]}...)\n"
        elif isinstance(search_result, str):
            # If tool returns string summary
            scout_context = search_result

    except Exception as e:
        logger.warning(f"Planner scout search failed: {e}")
        scout_context = "Could not perform initial scout search."

    # --- Generate Plan ---
    full_prompt = (
        PLANNER_SYSTEM_PROMPT
        + f"\n\nInitial Scout Findings (Use these URLs):\n{scout_context}"
    )

    messages = [
        SystemMessage(content=full_prompt),
        HumanMessage(content=context),
    ]

    response = await llm.ainvoke(messages)
    content = extract_content_string(response.content)

    try:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        plan = json.loads(clean_content)
    except Exception as e:
        logger.error(f"Failed to parse plan: {e}")
        # Fallback plan
        plan = {
            "tasks": [
                {
                    "name": "General Search",
                    "goal": f"Research {topic}",
                    "tool_hint": "tavily_search",
                    "tool_args": {"query": topic},
                }
            ]
        }

    return {"research_plan": plan, "messages": [response], "user_feedback": ""}


async def executor_node(state: AgentState):
    """
    Executes the research plan tasks using available tools.
    """
    plan = state.get("research_plan", {})
    tasks = plan.get("tasks", [])
    user_feedback = state.get("user_feedback", "")

    # Initialize cumulative context
    cumulative_context = f"Topic: {state.get('topic')}\n"
    if user_feedback:
        cumulative_context += f"User Guidance: {user_feedback}\n"

    gathered_data_log = []

    logger.info("Executor Node: Starting execution...")

    for i, task in enumerate(tasks):
        task_name = task.get("name")
        goal = task.get("goal")
        tool_hint = task.get("tool_hint")

        # Get args from plan (planner might have found the URL)
        plan_args = task.get("tool_args", {})

        logger.info(f"Executing Task {i+1}/{len(tasks)}: {task_name}")

        # Construct prompt with Date and Context
        prompt = EXECUTOR_SYSTEM_PROMPT_TEMPLATE.format(
            date=get_current_date(),
            task_name=task_name,
            goal=goal,
            previous_findings=cumulative_context[-6000:],  # Limit context
        )

        msg = [HumanMessage(content=prompt)]

        # Call LLM
        response = await llm_with_tools.ainvoke(msg)

        task_result = ""

        # 1. Handle Tool Calls
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                llm_args = tool_call["args"]

                logger.info(f"Tool Call: {tool_name}")

                # Find tool instance
                tool_func = next((t for t in tools if t.name == tool_name), None)

                if tool_func:
                    # Smart Arg Merging:
                    # If the planner gave a URL for scraping, FORCE it over the LLM's guess
                    final_args = llm_args.copy()
                    if tool_name == "scrape_competitor_page" and "url" in plan_args:
                        final_args["url"] = plan_args["url"]
                        logger.info(
                            f"  -> Enforcing URL from Plan: {final_args['url']}"
                        )
                    elif tool_name == "tavily_search" and "query" in plan_args:
                        # For search, LLM's query might be better tailored to context,
                        # but if plan was specific, we respect it.
                        pass

                    try:
                        res = tool_func.invoke(final_args)
                        task_result += (
                            f"\n[Tool Output from {tool_name}]:\n{str(res)}\n"
                        )
                    except Exception as e:
                        task_result += f"\nError executing {tool_name}: {str(e)}\n"
        else:
            content = extract_content_string(response.content)
            task_result += f"\nAnalysis: {content}\n"

        # 2. Update Context (Summarize to save tokens)
        summary = f"Task '{task_name}' Result: {task_result[:800]}..."
        cumulative_context += f"\n{summary}\n"

        # 3. Log Full Data
        gathered_data_log.append(
            f"### Task: {task_name}\n**Goal:** {goal}\n\n{task_result}"
        )

    return {"gathered_data": gathered_data_log}


async def reporter_node(state: AgentState):
    """
    Aggregates data and writes the final report.
    """
    topic = state.get("topic")
    data = state.get("gathered_data", [])
    feedback = state.get("user_feedback", "")

    logger.info("Reporter Node: generating final report")

    data_str = "\n\n".join(data)

    prompt = REPORTER_SYSTEM_PROMPT_TEMPLATE.format(
        date=get_current_date(), topic=topic, data_str=data_str, feedback=feedback
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    content = extract_content_string(response.content)
    return {"final_report": content}


# --- Graph Construction ---


def should_continue(state: AgentState):
    feedback = state.get("user_feedback", "").lower().strip()
    approval_keywords = [
        "approve",
        "approved",
        "ok",
        "okay",
        "yes",
        "go",
        "proceed",
        "",
    ]
    if not feedback or feedback in approval_keywords:
        return "executor"
    return "planner"


def build_investigator_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("reporter", reporter_node)

    builder.add_edge(START, "planner")

    builder.add_conditional_edges(
        "planner", should_continue, {"executor": "executor", "planner": "planner"}
    )

    builder.add_edge("executor", "reporter")
    builder.add_edge("reporter", END)

    # Compile with interrupt AFTER planner to allow user review
    graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_after=["planner"],
    )

    return graph
