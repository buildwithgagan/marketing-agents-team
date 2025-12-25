from __future__ import annotations

from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .prompts import MASTER_PLANNER_SYSTEM, MASTER_SYNTH_SYSTEM
from .state import BrewState, TaskPlan, WorkerReport, WorkerState
from .workers import (
    create_analytics_worker_agent,
    create_content_worker_agent,
    create_general_worker_agent,
    create_research_worker_agent,
    create_social_worker_agent,
)


def create_brew_graph(
    model: BaseChatModel,
    tools: List[BaseTool],
    checkpointer: MemorySaver | None = None,
):
    """
    Brew mode: tool-less master supervisor + parallel Deep Agents workers.

    - planner: tool-less master, structured plan
    - workers: deepagents workers with tools (Tavily MCP)
    - synthesizer: tool-less master, streams final response
    """

    # --- Create worker agents (tools ONLY here) ---
    research_agent = create_research_worker_agent(model, tools)
    content_agent = create_content_worker_agent(model, tools)
    analytics_agent = create_analytics_worker_agent(model, tools)
    social_agent = create_social_worker_agent(model, tools)
    general_agent = create_general_worker_agent(model)

    # --- Nodes ---
    async def planner(state: BrewState) -> dict:
        # Extract last user message
        user_text = ""
        for msg in reversed(state.get("messages", [])):
            if hasattr(msg, "content"):
                user_text = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                break
            if isinstance(msg, dict) and "content" in msg:
                user_text = str(msg["content"])
                break

        # Heuristic routing:
        # - casual greetings / short chat -> direct response (no workers)
        # - general questions (no web needed) -> general worker (no Tavily)
        # - otherwise: structured plan
        user_lower = user_text.lower().strip()
        tokens = [
            t for t in user_lower.replace("?", " ").replace("!", " ").split() if t
        ]
        simple_greetings = {
            "hi",
            "hello",
            "hey",
            "yo",
            "sup",
            "howdy",
            "kiddan",
            "kiddaan",
            "tussin",
            "tusin",
        }
        action_keywords = [
            "research",
            "search",
            "find",
            "latest",
            "sources",
            "cite",
            "tavily",
            "news",
            "trend",
            "twitter",
            "tweet",
            "x",
            "linkedin",
            "post",
            "campaign",
            "strategy",
            "analyze",
            "analysis",
            "benchmark",
            "kpi",
            "metrics",
        ]
        is_action = any(k in user_lower for k in action_keywords)
        is_greeting_like = (len(tokens) <= 6) and any(
            t in simple_greetings for t in tokens
        )
        simple = is_greeting_like or (
            len(tokens) <= 6
            and not is_action
            and any(
                k in user_lower
                for k in ["who are you", "what can you do", "how are you"]
            )
        )
        if simple:
            return {
                "status": "Direct response",
                "task_plan": TaskPlan(reasoning="Direct response", tasks=[]),
            }

        # Use general worker for non-web, non-marketing small questions
        if not is_action and len(tokens) <= 25:
            return {
                "task_plan": TaskPlan(
                    reasoning="General question - no internet needed",
                    tasks=[
                        {
                            "worker": "general",
                            "task": user_text,
                            "priority": 1,
                        }
                    ],
                ),
                "status": "Planning complete: 1 tasks assigned",
            }

        planner_model = model.with_structured_output(TaskPlan)
        plan: TaskPlan = await planner_model.ainvoke(
            [
                SystemMessage(content=MASTER_PLANNER_SYSTEM),
                HumanMessage(content=f"Create a concise task plan for: {user_text}"),
            ]
        )
        return {
            "task_plan": plan,
            "status": f"Planning complete: {len(plan.tasks)} tasks assigned",
        }

    def dispatch_workers(state: BrewState) -> List[Send]:
        plan = state.get("task_plan")
        if not plan or not getattr(plan, "tasks", None):
            return [Send("synthesizer", state)]

        sends: List[Send] = []
        for assignment in plan.tasks:
            node = f"{assignment.worker}_worker"
            sends.append(Send(node, {"assignment": assignment}))
        return sends

    async def _run_worker(agent, state: WorkerState, worker_name: str) -> dict:
        assignment = state.get("assignment")
        if not assignment:
            return {
                "worker_reports": [
                    WorkerReport(
                        worker=worker_name,
                        task="",
                        status="failed",
                        result="Missing assignment.",
                    )
                ]
            }

        try:
            # Run deep agent; it can use tools internally.
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": assignment.task}]}
            )
            # deepagents returns a LangGraph-like state; try common shapes
            text = ""
            if isinstance(result, dict) and "messages" in result and result["messages"]:
                last = result["messages"][-1]
                if isinstance(last, dict):
                    text = str(last.get("content", ""))
                else:
                    text = getattr(last, "content", "") if last else ""
            if not text:
                text = str(result)

            return {
                "worker_reports": [
                    WorkerReport(
                        worker=worker_name,
                        task=assignment.task,
                        status="success",
                        result=text,
                    )
                ]
            }
        except Exception as e:
            return {
                "worker_reports": [
                    WorkerReport(
                        worker=worker_name,
                        task=assignment.task,
                        status="failed",
                        result=f"Worker failed: {e}",
                    )
                ]
            }

    async def research_worker(state: WorkerState) -> dict:
        return await _run_worker(research_agent, state, "research")

    async def content_worker(state: WorkerState) -> dict:
        return await _run_worker(content_agent, state, "content")

    async def analytics_worker(state: WorkerState) -> dict:
        return await _run_worker(analytics_agent, state, "analytics")

    async def social_worker(state: WorkerState) -> dict:
        return await _run_worker(social_agent, state, "social")

    async def general_worker(state: WorkerState) -> dict:
        return await _run_worker(general_agent, state, "general")

    async def synthesizer(state: BrewState) -> dict:
        # Extract user request (best-effort)
        user_text = ""
        for msg in reversed(state.get("messages", [])):
            if hasattr(msg, "content"):
                user_text = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                break
            if isinstance(msg, dict) and "content" in msg:
                user_text = str(msg["content"])
                break

        reports = state.get("worker_reports", [])
        reports_text = "\n\n".join(
            [
                f"## {r.worker} ({r.status})\nTask: {r.task}\n\n{r.result}"
                for r in reports
            ]
        )

        # Use streaming-enabled model so callbacks emit token events.
        messages = [
            SystemMessage(content=MASTER_SYNTH_SYSTEM),
            HumanMessage(
                content=f"User request:\n{user_text}\n\nWorker reports:\n{reports_text}"
            ),
        ]

        resp = await model.ainvoke(messages)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return {"final_response": text, "status": "Synthesis complete"}

    # --- Build graph ---
    builder = StateGraph(BrewState)
    builder.add_node("planner", planner)
    builder.add_node("research_worker", research_worker)
    builder.add_node("content_worker", content_worker)
    builder.add_node("analytics_worker", analytics_worker)
    builder.add_node("social_worker", social_worker)
    builder.add_node("general_worker", general_worker)
    builder.add_node("synthesizer", synthesizer)

    builder.add_edge(START, "planner")
    builder.add_conditional_edges(
        "planner",
        dispatch_workers,
        [
            "research_worker",
            "content_worker",
            "analytics_worker",
            "social_worker",
            "general_worker",
            "synthesizer",
        ],
    )

    # Workers write to shared state key worker_reports (reducer) and converge to synthesizer
    builder.add_edge("research_worker", "synthesizer")
    builder.add_edge("content_worker", "synthesizer")
    builder.add_edge("analytics_worker", "synthesizer")
    builder.add_edge("social_worker", "synthesizer")
    builder.add_edge("general_worker", "synthesizer")
    builder.add_edge("synthesizer", END)

    return (
        builder.compile(checkpointer=checkpointer)
        if checkpointer
        else builder.compile()
    )
