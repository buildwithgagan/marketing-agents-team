import json
import os
from typing import Any, Dict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.runnables import ConfigurableField
from dotenv import load_dotenv

load_dotenv()
from app.tools.marketing import (
    get_autocomplete_suggestions,
    get_google_trends,
    tavily_search,
    scrape_competitor_page,
)
from .state import AgentState
from .schemas import ResearchPlan, UserIntent
from .prompts import (
    get_current_date,
    PLANNER_SYSTEM_PROMPT,
    EXECUTOR_SYSTEM_PROMPT_TEMPLATE,
    REPORTER_SYSTEM_PROMPT_TEMPLATE,
)


# --- Helper ---
def extract_content_string(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join([c.get("text", "") for c in content if c.get("type") == "text"])
    return str(content)


# --- Config ---
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ ERROR: OPENAI_API_KEY missing from .env")

base_llm = ChatOpenAI(model="gpt-4.1-mini", api_key=api_key)

llm = base_llm.configurable_fields(
    model_name=ConfigurableField(id="model_name"),
    reasoning=ConfigurableField(id="reasoning"),
    output_version=ConfigurableField(id="output_version"),
)

tools = [
    tavily_search,
    scrape_competitor_page,
    get_google_trends,
    get_autocomplete_suggestions,
]
llm_with_tools = llm.bind_tools(tools)

# --- Nodes ---


async def planner_node(state: AgentState):
    topic = state.get("topic", "Unknown Topic")
    feedback = state.get("user_feedback", "")
    existing_plan = state.get("research_plan", {})

    print(f"\n🔹 [Planner] ACTIVE for: {topic}")
    if feedback:
        print(f"   📝 Feedback received: {feedback}")

    if feedback and existing_plan and existing_plan.get("tasks"):
        intent_llm = base_llm.with_structured_output(UserIntent)
        intent_prompt = (
            f"User Feedback: {feedback}\n\n"
            "Analyze the user's feedback regarding a research plan. "
            "Determine if they are APPROVING the plan to proceed immediately, "
            "or requesting CHANGES/UPDATES to the plan.\n"
            "- If they say 'ok', 'proceed', 'looks good', 'approved', etc. -> action='approve', feedback_summary=None\n"
            "- If they ask for changes, additions, removals, or clarifications -> action='update', feedback_summary='Summary of changes needed...'"
        )
        try:
            intent_result = await intent_llm.ainvoke(
                [HumanMessage(content=intent_prompt)]
            )

            if intent_result.action == "approve":
                print(f"   ⏭️ [Planner] LLM classified intent as 'approve'. Proceeding with existing plan.")
                return {"research_plan": existing_plan, "user_feedback": ""}

            print(f"   🔄 [Planner] LLM classified intent as 'update'. Modifying plan...")
        except Exception as e:
            print(f"   ⚠️ [Planner] Intent classification failed: {e}. Defaulting to update.")
            pass

    if existing_plan and feedback:
        import json
        plan_str = json.dumps(existing_plan, indent=2)
        context = (
            f"Topic: {topic}\n"
            f"Existing Plan: {plan_str}\n"
            f"User Feedback: {feedback}\n\n"
            "INSTRUCTION: Update the plan according to user feedback. Do not lose existing valid tasks unless asked."
        )
    else:
        context = f"Topic: {topic}\nFeedback: {feedback}"

    # Use function_calling for flexible args
    structured_llm = llm.with_structured_output(ResearchPlan, method="function_calling")

    try:
        plan_object = await structured_llm.ainvoke(
            [
                SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=context),
            ]
        )

        plan = plan_object.model_dump()
        print(f"   ✅ [Planner] Generated {len(plan['tasks'])} tasks:")
        for t in plan["tasks"]:
            print(f"      - {t['name']}")

    except Exception as e:
        print(f"   ❌ [Planner] Error: {e}")
        plan = {
            "tasks": [
                {
                    "name": "Fallback",
                    "goal": "Error recovery",
                    "tool_hint": "tavily_search",
                    "tool_args": {"query": topic},
                }
            ]
        }

    return {"research_plan": plan}


async def executor_node(state: AgentState):
    topic = state.get("topic", "Unknown Topic")
    plan = state.get("research_plan", {})
    tasks = plan.get("tasks", [])

    print(f"\n🔹 [Executor] Processing {len(tasks)} tasks...")

    context = f"Topic: {topic}\n"
    data_log = []

    for i, task in enumerate(tasks):
        task_name = task.get("name")
        plan_args = task.get("tool_args", {})
        task_goal = task.get("goal")

        print(f"   ▶️ [{i+1}/{len(tasks)}] {task_name}")

        prompt_content = EXECUTOR_SYSTEM_PROMPT_TEMPLATE.format(
            date=get_current_date(),
            task_name=task_name,
            goal=task_goal,
            previous_findings=context[-6000:],
            topic=topic,
        )

        task_messages = [HumanMessage(content=prompt_content)]
        task_res = ""

        for turn in range(3):
            response = await llm_with_tools.ainvoke(task_messages)
            task_messages.append(response)

            if response.tool_calls:
                for tc in response.tool_calls:
                    t_name = tc["name"]
                    t_args = tc["args"]
                    t_id = tc["id"]

                    if turn == 0 and t_name == "scrape_competitor_page" and "url" in plan_args:
                        t_args["url"] = plan_args["url"]
                        print(f"      🔗 Enforcing URL: {t_args['url']}")

                    print(f"      🛠️ Calling: {t_name}")
                    tool_func = next((t for t in tools if t.name == t_name), None)

                    tool_output = "Error: Tool not found."
                    if tool_func:
                        try:
                            tool_output = tool_func.invoke(t_args)
                            tool_output_str = str(tool_output)
                            if len(tool_output_str) > 5000:
                                tool_output_str = tool_output_str[:5000] + "... (truncated)"

                            task_res += f"\n[Tool {t_name} Output]: {tool_output_str[:500]}\n"
                        except Exception as e:
                            print(f"      ❌ Tool Error: {e}")
                            tool_output = f"Error: {e}"
                            task_res += f"\nError {t_name}: {e}\n"

                    task_messages.append(
                        ToolMessage(tool_call_id=t_id, content=str(tool_output))
                    )

                # No tool calls = Final Answer
                content = extract_content_string(response.content)
                task_res += f"\nAnalysis: {content}\n"
                break

        if not task_res:
            task_res = "Task completed with tool actions but no final summary."

        context += f"\nTask '{task_name}' Summary: {task_res[:500]}...\n"
        data_log.append(f"### {task_name}\n{task_res}")

    return {"gathered_data": data_log, "user_feedback": ""}


async def reporter_node(state: AgentState):
    print("\n🔹 [Reporter] Writing final report...")
    data_str = "\n\n".join(state.get("gathered_data", []))
    prompt = REPORTER_SYSTEM_PROMPT_TEMPLATE.format(
        date=get_current_date(),
        topic=state.get("topic", "Unknown"),
        data_str=data_str,
        feedback=state.get("user_feedback", ""),
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    content = extract_content_string(response.content)
    print("   ✅ [Reporter] Done.")
    return {"final_report": content}


# --- Graph ---
def should_continue(state: AgentState):
    fb = state.get("user_feedback", "").lower().strip()
    if not fb:
        return "executor"
    return "executor"


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

    return builder.compile(checkpointer=checkpointer, interrupt_after=["planner"])


def build_executor_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(AgentState)
    builder.add_node("executor", executor_node)
    builder.add_node("reporter", reporter_node)

    builder.add_edge(START, "executor")
    builder.add_edge("executor", "reporter")
    builder.add_edge("reporter", END)

    return builder.compile(checkpointer=checkpointer)
