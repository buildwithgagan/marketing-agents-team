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
    create_report_worker_agent,
    create_reviewer_agent,
    create_strategist_agent,
)


def create_brew_graph(
    model: BaseChatModel,
    tools: List[BaseTool],
    checkpointer: MemorySaver | None = None,
):
    """
    Brew mode: tool-less master supervisor + sequential Deep Agents workers.

    - planner: tool-less master, structured plan
    - workers: deepagents workers with tools (Tavily MCP), executed sequentially by priority
    - synthesizer: tool-less master, streams final response
    """

    # --- Create worker agents (tools ONLY here) ---
    research_agent = create_research_worker_agent(model, tools)
    content_agent = create_content_worker_agent(model, tools)
    analytics_agent = create_analytics_worker_agent(model, tools)
    social_agent = create_social_worker_agent(model, tools)
    report_agent = create_report_worker_agent(model)
    reviewer_agent = create_reviewer_agent(model)
    strategist_agent = create_strategist_agent(model)
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
        # Sort tasks by priority (1 highest) to ensure deterministic sequential execution
        if getattr(plan, "tasks", None):
            sorted_tasks = sorted(
                plan.tasks, key=lambda t: getattr(t, "priority", 2) or 2
            )
            plan = TaskPlan(reasoning=plan.reasoning, tasks=sorted_tasks)
        return {
            "task_plan": plan,
            "status": f"Planning complete: {len(plan.tasks)} tasks assigned",
            "next_task_index": 0,
        }

    def task_router(state: BrewState) -> dict:
        """Route to the next worker sequentially based on task priority order."""
        plan = state.get("task_plan")
        idx = state.get("next_task_index", 0)
        if not plan or not getattr(plan, "tasks", None):
            return {"route": "synthesizer"}

        tasks = plan.tasks
        # Clamp index in case of drift
        if idx >= len(tasks):
            return {"route": "synthesizer"}

        assignment = tasks[idx]
        return {
            "route": f"{assignment.worker}_worker",
            "assignment": assignment,
        }

    async def _run_worker(
        agent,
        state: WorkerState,
        worker_name: str,
        override_task: str = None,
        increment_index: bool = True,
    ) -> dict:
        assignment = state.get("assignment")
        task_text = override_task if override_task else (assignment.task if assignment else "")

        if not task_text:
            return {
                "worker_reports": [
                    WorkerReport(
                        worker=worker_name,
                        task="",
                        status="failed",
                        result="Missing assignment.",
                    )
                ],
                "next_task_index": state.get("next_task_index", 0) + (1 if increment_index else 0),
            }

        try:
            # Run deep agent; it can use tools internally.
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": task_text}]}
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
                ],
                "next_task_index": state.get("next_task_index", 0) + (1 if increment_index else 0),
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
                ],
                "next_task_index": state.get("next_task_index", 0) + (1 if increment_index else 0),
            }

    async def research_worker(state: WorkerState) -> dict:
        # 1. Prepare Delta Prompt
        input_msg = state.get("assignment").task
        feedback = state.get("critique_feedback", "")
        existing_data = state.get("research_data", "")

        if feedback:
            # Round 2+: Incremental Research
            input_msg = (
                f"Original Task: {input_msg}\n\n"
                f"EXISTING FINDINGS:\n{existing_data}\n\n"
                f"CRITIQUE (MISSING INFO): {feedback}\n\n"
                f"INSTRUCTION: Search ONLY for the missing items. Append them."
            )
            
        # 2. Run Worker (no index increment)
        res = await _run_worker(
            research_agent, state, "research", override_task=input_msg, increment_index=False
        )
        
        # 3. Accumulate Data (Append, don't overwrite)
        new_text = res.get("worker_reports")[0].result
        combined_text = existing_data + "\n\n" + new_text if existing_data else new_text
        
        current_iter = state.get("iteration_count", 0)
        return {**res, "research_data": combined_text, "iteration_count": current_iter + 1}

    async def reviewer_worker(state: WorkerState) -> dict:
        # Reviewer analyzes the research data
        # No index increment
        research_text = state.get("research_data", "")
        res = await _run_worker(
            reviewer_agent, state, "reviewer", increment_index=False
        )
        # Extract critique result
        critique = res.get("worker_reports")[0].result
        return {**res, "critique_feedback": critique}

    async def strategist_worker(state: WorkerState) -> dict:
        # Strategist IS the node that completes the task logic.
        # So we increment index here.
        return await _run_worker(strategist_agent, state, "strategist", increment_index=True)

    async def content_worker(state: WorkerState) -> dict:
        return await _run_worker(content_agent, state, "content")

    async def analytics_worker(state: WorkerState) -> dict:
        return await _run_worker(analytics_agent, state, "analytics")

    async def social_worker(state: WorkerState) -> dict:
        return await _run_worker(social_agent, state, "social")

    async def report_worker(state: WorkerState) -> dict:
        return await _run_worker(report_agent, state, "report")

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
    builder.add_node("task_router", task_router)
    builder.add_node("research_worker", research_worker)
    builder.add_node("reviewer_worker", reviewer_worker)
    builder.add_node("strategist_worker", strategist_worker)
    builder.add_node("content_worker", content_worker)
    builder.add_node("analytics_worker", analytics_worker)
    builder.add_node("social_worker", social_worker)
    builder.add_node("report_worker", report_worker)
    builder.add_node("general_worker", general_worker)
    builder.add_node("synthesizer", synthesizer)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "task_router")
    builder.add_conditional_edges(
        "task_router",
        lambda state: state.get("route", "synthesizer"),
        {
            "research_worker": "research_worker",
            "reviewer_worker": "reviewer_worker",
            "strategist_worker": "strategist_worker",
            "content_worker": "content_worker",
            "analytics_worker": "analytics_worker",
            "analytics_worker": "analytics_worker",
            "social_worker": "social_worker",
            "report_worker": "report_worker",
            "general_worker": "general_worker",
            "synthesizer": "synthesizer",
        },
    )

    # Debate Loop Logic
    def should_continue_debate(state: BrewState):
        feedback = state.get("critique_feedback", "")
        iterations = state.get("iteration_count", 0)
        
        if "REJECT" in feedback and iterations < 3:
            return "research_worker"
        return "strategist_worker"

    # Research -> Reviewer -> (Loop) or Strategist
    builder.add_edge("research_worker", "reviewer_worker")
    builder.add_conditional_edges(
        "reviewer_worker",
        should_continue_debate,
        {
            "research_worker": "research_worker",
            "strategist_worker": "strategist_worker"
        }
    )
    # Strategist -> Report -> End (or Router if needed, for simplicity we go to Router/End)
    # Actually current flow goes back to Task Router.
    # We want Research task to stay in "Research Phase" until Strategist is done.
    # So we bypass task_router for the internal loop.
    builder.add_edge("strategist_worker", "task_router")

    # builder.add_edge("research_worker", "task_router") # REMOVED: Managed by loop now
    builder.add_edge("content_worker", "task_router")
    builder.add_edge("analytics_worker", "task_router")
    builder.add_edge("analytics_worker", "task_router")
    builder.add_edge("social_worker", "task_router")
    builder.add_edge("report_worker", "task_router")
    builder.add_edge("general_worker", "task_router")
    builder.add_edge("synthesizer", END)

    return (
        builder.compile(checkpointer=checkpointer)
        if checkpointer
        else builder.compile()
    )
