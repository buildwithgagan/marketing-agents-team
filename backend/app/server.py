from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from .agent import agent_manager
import json
from contextlib import asynccontextmanager
import os
import logging
from typing import Optional
import asyncio

# Configure logging (ensure handler even when uvicorn overrides root config)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("deepagent-api")
DEBUG_EVENTS = os.getenv("DEEPAGENT_DEBUG_EVENTS", "").strip() == "1"
logger.setLevel(logging.DEBUG if DEBUG_EVENTS else logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Agent Manager...")
    await agent_manager.initialize()
    logger.info("Agent Manager initialized.")
    yield
    # Shutdown
    logger.info("Cleaning up Agent Manager...")
    await agent_manager.cleanup()
    logger.info("Cleanup complete.")


app = FastAPI(lifespan=lifespan)

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    thread_id = data.get("thread_id", "default-thread")
    model_name = data.get("model", "gpt-4.1")
    thinking_enabled = data.get("thinking", False)
    mode = data.get("mode")  # Can be null/None for brew mode (default)

    last_message = messages[-1] if messages else {"content": ""}
    user_input = last_message.get("content", "")

    # Determine effective mode
    # If mode is null/None, use "brew" as default
    effective_mode = mode if mode else "brew"

    # Prepare inputs based on mode
    if effective_mode.startswith("brew"):
        # Brew mode uses BrewState format
        inputs = {
            "messages": [{"role": "user", "content": user_input}],
            "worker_reports": [],
        }
    else:
        # Other modes use standard message format
        inputs = {"messages": [{"role": "user", "content": user_input}]}

    # Prepare configuration
    config = {
        "configurable": {
            "thread_id": thread_id,
            "model_name": model_name,
            "mode": effective_mode,
        }
    }

    # If it's a reasoning model (GPT-5 series) and thinking is ENABLED
    if model_name.startswith("gpt-5") and thinking_enabled:
        reasoning_config = {"effort": "high", "summary": "auto"}
        config["configurable"]["reasoning"] = reasoning_config
        config["configurable"]["output_version"] = "responses/v1"
        config["configurable"]["reasoning_effort"] = "high"
    elif model_name.startswith("gpt-5"):
        # For GPT-5 with thinking DISABLED, we still use responses/v1 but MINIMAL effort
        config["configurable"]["reasoning"] = {"effort": "low"}
        config["configurable"]["output_version"] = "responses/v1"
        config["configurable"]["reasoning_effort"] = "low"

    # Handle o1/o3 which ALSO support reasoning_effort
    if (
        model_name.startswith("o1") or model_name.startswith("o3")
    ) and thinking_enabled:
        config["configurable"]["reasoning_effort"] = "high"
    elif model_name.startswith("o1") or model_name.startswith("o3"):
        config["configurable"]["reasoning_effort"] = "low"

    logger.info(
        f"User Query (Thread: {thread_id}, Model: {model_name}, Mode: {effective_mode}, Thinking: {thinking_enabled}): {user_input}"
    )

    # Get the appropriate agent for the mode
    agent = agent_manager.get_agent(effective_mode)

    async def event_generator():
        # Track current node to filter internal streaming
        current_node = ""

        # For brew mode, we only want to stream from the synthesizer, not workers
        is_brew_mode = effective_mode == "brew"

        # Track what we've already emitted to prevent duplicates
        emitted_plan = False
        emitted_final = False
        emitted_workers = set()  # Track which workers we've reported
        last_status: Optional[str] = None
        emitted_synth_tokens = False

        # Internal nodes that use structured output - don't stream their tokens
        # Planner uses structured output, but synthesizer should stream
        internal_nodes = {
            "planner",
            "StructuredOutput",
        }

        # Worker nodes - their output is captured via worker_reports, not streaming
        brew_worker_nodes = {
            "research_worker",
            "content_worker",
            "analytics_worker",
            "social_worker",
            "general_worker",
        }

        # Track if we're in planner phase (to block its JSON tokens)
        in_planner_phase = False
        # Track if we're in synthesis phase (to allow nested model streaming)
        in_synth_phase = False

        # Verbose per-event tracing is opt-in (very noisy)
        debug_events = DEBUG_EVENTS

        try:
            async for event in agent.astream_events(
                inputs, config=config, version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")

                # Debug logging for event flow (disabled by default)
                if debug_events:
                    logger.debug(f"Event received: kind={kind}, name={name}")

                # Track current node
                if kind == "on_chain_start" and name:
                    current_node = name
                    # Track planner phase
                    if name == "planner":
                        in_planner_phase = True
                    if name == "synthesizer":
                        in_synth_phase = True

                # Clear current node when a chain ends (avoid stale filtering)
                if kind == "on_chain_end" and name and name == current_node:
                    current_node = ""
                    # Clear planner phase when planner ends
                    if name == "planner":
                        in_planner_phase = False
                    if name == "synthesizer":
                        in_synth_phase = False

                # === BREW MODE SPECIFIC EVENTS ===

                # Phase/Status updates for brew mode
                if kind == "on_chain_end":
                    output = event["data"].get("output", {})

                    if not isinstance(output, dict):
                        continue

                    # Task plan (only from planner) - stream incrementally
                    if name == "planner":
                        if (
                            "task_plan" in output
                            and output.get("task_plan")
                            and not emitted_plan
                        ):
                            task_plan = output["task_plan"]
                            if hasattr(task_plan, "tasks") and task_plan.tasks:
                                reasoning = getattr(task_plan, "reasoning", "")
                                first = True
                                for t in task_plan.tasks:
                                    yield json.dumps(
                                        {
                                            "type": "plan_delta",
                                            "worker": t.worker,
                                            "task": t.task,
                                            "priority": t.priority,
                                            "reasoning": reasoning if first else "",
                                        }
                                    ) + "\n"
                                    first = False
                                emitted_plan = True

                    # Worker reports (only from worker nodes) with deduplication
                    if name.endswith("_worker"):
                        if "worker_reports" in output:
                            for report in output.get("worker_reports", []):
                                if hasattr(report, "worker"):
                                    worker_key = f"{report.worker}:{report.task[:50]}"
                                    if worker_key not in emitted_workers:
                                        yield json.dumps(
                                            {
                                                "type": "worker_complete",
                                                "worker": report.worker,
                                                "task": report.task,
                                                "status": report.status,
                                            }
                                        ) + "\n"
                                        emitted_workers.add(worker_key)

                    # Status updates (dedupe)
                    if "status" in output:
                        status_val = str(output["status"])
                        if status_val and status_val != last_status:
                            yield json.dumps(
                                {"type": "status", "content": status_val}
                            ) + "\n"
                            last_status = status_val

                    # Final response
                    if (
                        "final_response" in output
                        and output.get("final_response")
                        and not emitted_final
                    ):
                        # Direct response from planner (simple queries)
                        task_plan = (
                            output.get("task_plan") if name == "planner" else None
                        )
                        is_direct_response = (
                            name == "planner"
                            and task_plan
                            and hasattr(task_plan, "tasks")
                            and not task_plan.tasks
                        )

                        if name == "synthesizer" and is_brew_mode:
                            # If we didn't get real token events from the model, simulate streaming
                            # by chunking the final response. This keeps UX consistent with other modes.
                            if not emitted_synth_tokens:
                                text = str(output["final_response"])
                                chunk_size = 32
                                for i in range(0, len(text), chunk_size):
                                    yield json.dumps(
                                        {
                                            "type": "content",
                                            "content": text[i : i + chunk_size],
                                        }
                                    ) + "\n"
                                    await asyncio.sleep(0)
                                emitted_final = True
                            else:
                                # Synthesizer already streamed tokens; don't emit full final chunk.
                                emitted_final = True
                        elif is_direct_response or not is_brew_mode:
                            yield json.dumps(
                                {
                                    "type": "content",
                                    "content": output["final_response"],
                                }
                            ) + "\n"
                            emitted_final = True

                    # Handle TodoListMiddleware for other modes
                    if name == "TodoListMiddleware":
                        if (
                            output
                            and isinstance(output, dict)
                            and "todo_list" in output
                        ):
                            todo_data = output["todo_list"]
                            if isinstance(todo_data, dict) and "todos" in todo_data:
                                todo_data = todo_data["todos"]
                            if not isinstance(todo_data, list):
                                todo_data = [str(todo_data)]
                            yield json.dumps(
                                {"type": "plan", "content": todo_data}
                            ) + "\n"

                # Token streaming
                if kind == "on_chat_model_stream":
                    # Prefer the event name to determine the node; fallback to current_node
                    stream_name = name or current_node

                    # Skip streaming from internal orchestration nodes
                    if stream_name in internal_nodes:
                        continue

                    # Brew mode: ONLY allow token streaming from synthesizer.
                    # This prevents worker deepagents tokens (and planner JSON) from leaking into the UI.
                    if is_brew_mode and not in_synth_phase:
                        continue

                    # Block planner's structured output JSON tokens
                    # The planner uses structured output, which streams as JSON tokens
                    # We only want the formatted plan event, not the raw JSON
                    if is_brew_mode and (current_node == "planner" or in_planner_phase):
                        continue

                    chunk = event["data"].get("chunk")
                    if chunk:
                        thought = None

                        # Handle Responses API format (list-based content)
                        if isinstance(chunk.content, list):
                            for block in chunk.content:
                                block_type = block.get("type")
                                if block_type == "reasoning":
                                    # Streaming reasoning summary text if available
                                    thought = block.get("text") or block.get("content")
                                    if not thought and block.get("summary"):
                                        summaries = block.get("summary")
                                        if (
                                            isinstance(summaries, list)
                                            and len(summaries) > 0
                                        ):
                                            thought = "\n".join(
                                                [
                                                    str(s.get("text", ""))
                                                    for s in summaries
                                                    if s.get("text")
                                                ]
                                            )

                                elif block_type == "text":
                                    content = block.get("text", "")
                                    if content:
                                        # Block planner JSON tokens even in text blocks
                                        if is_brew_mode and (
                                            current_node == "planner"
                                            or in_planner_phase
                                        ):
                                            # Check if this looks like planner JSON
                                            if (
                                                '{"reasoning"' in content
                                                or '"reasoning"' in content
                                                or '"worker":"' in content
                                            ):
                                                continue
                                        yield json.dumps(
                                            {"type": "content", "content": content}
                                        ) + "\n"
                                        if is_brew_mode and in_synth_phase:
                                            emitted_synth_tokens = True

                        # Extract reasoning content from attributes (Fallback & Standard)
                        attr_thought = (
                            getattr(chunk, "reasoning_content", None)
                            or chunk.additional_kwargs.get("reasoning_content")
                            or chunk.additional_kwargs.get("thought")
                            or chunk.additional_kwargs.get("thinking")
                        )

                        if attr_thought:
                            thought = (
                                (thought + "\n" + attr_thought)
                                if thought
                                else attr_thought
                            )

                        if thought:
                            yield json.dumps(
                                {"type": "thought", "content": thought}
                            ) + "\n"

                        # Standard string content
                        if isinstance(chunk.content, str) and chunk.content:
                            content = chunk.content

                            # Block planner JSON tokens - check for planner JSON patterns
                            if is_brew_mode and (
                                current_node == "planner" or in_planner_phase
                            ):
                                # Check if this looks like planner structured output JSON
                                stripped = content.strip()
                                if (
                                    stripped.startswith('{"reasoning"')
                                    or stripped.startswith('"reasoning"')
                                    or stripped.startswith('{"')
                                    and ('"worker"' in content or '"task"' in content)
                                    or '"worker":"' in content
                                    or '"task":"' in content
                                ):
                                    continue

                            # Only skip if it's a complete JSON object (not just text with brackets)
                            stripped = content.strip()
                            is_complete_json = (
                                stripped.startswith('{"') and stripped.endswith("}")
                            ) or (stripped.startswith("[{") and stripped.endswith("]"))
                            if not is_complete_json:
                                yield json.dumps(
                                    {"type": "content", "content": content}
                                ) + "\n"
                                if is_brew_mode and in_synth_phase:
                                    emitted_synth_tokens = True

                # Node transition / Status updates
                elif kind == "on_chain_start":
                    # Brew mode: emit explicit worker_start for UI
                    if is_brew_mode and name.endswith("_worker"):
                        raw_input = event["data"].get("input", {})
                        worker = name.replace("_worker", "")
                        task = ""
                        if isinstance(raw_input, dict) and "assignment" in raw_input:
                            assignment = raw_input.get("assignment")
                            if hasattr(assignment, "task"):
                                task = assignment.task
                            elif isinstance(assignment, dict):
                                task = str(assignment.get("task", ""))
                        yield json.dumps(
                            {"type": "worker_start", "worker": worker, "task": task}
                        ) + "\n"

                    # Brew mode specific nodes
                    brew_status_map = {
                        "planner": "🎯 Master Orchestrator planning tasks...",
                        "research_worker": "🔍 Research Specialist working...",
                        "content_worker": "✍️ Content Strategist working...",
                        "analytics_worker": "📊 Analytics Specialist working...",
                        "social_worker": "📱 Social Media Strategist working...",
                        "general_worker": "💬 General Assistant working...",
                        "synthesizer": "🧩 Synthesizing final response...",
                    }

                    # Legacy mode nodes
                    legacy_status_map = {
                        "research-agent": "Deep researching using Tavily...",
                        "crawl-agent": "Crawling website data...",
                        "master-agent": "Master Orchestrator planning...",
                        "agent": "Thinking and planning...",
                    }

                    # Check brew mode nodes first
                    if name in brew_status_map:
                        yield json.dumps(
                            {"type": "status", "content": brew_status_map[name]}
                        ) + "\n"
                    elif name in legacy_status_map:
                        yield json.dumps(
                            {"type": "status", "content": legacy_status_map[name]}
                        ) + "\n"

                # Tool calls (Start)
                elif kind == "on_tool_start":
                    tool_name = name or "tool"

                    # Filter out internal planning tools from the search progress UI
                    if tool_name in ["write_todos", "update_todos"]:
                        continue
                    # Hide deepagents internal delegation tool noise in brew mode
                    if is_brew_mode and tool_name == "task":
                        continue

                    raw_input = event["data"].get("input", "")

                    # Clean up input for the UI
                    tool_input = ""
                    if isinstance(raw_input, dict):
                        tool_input = raw_input.get("query") or raw_input.get("url")
                        if not tool_input:
                            ui_input = {
                                k: v
                                for k, v in raw_input.items()
                                if k not in ["runtime", "state"]
                            }
                            tool_input = json.dumps(ui_input)
                    else:
                        tool_input = str(raw_input)

                    # Truncate if too long
                    if len(tool_input) > 80:
                        tool_input = tool_input[:77] + "..."

                    logger.info(f"Tool Call Start: {tool_name} with {tool_input}")
                    yield json.dumps(
                        {
                            "type": "tool_start",
                            "tool": tool_name,
                            "content": f"Running {tool_name}...",
                            "input": tool_input,
                            "tool_name": tool_name,
                        }
                    ) + "\n"

                # Tool results (End)
                elif kind == "on_tool_end":
                    tool_name = name or "tool"
                    if tool_name in ["write_todos", "update_todos"]:
                        continue
                    if is_brew_mode and tool_name == "task":
                        continue

                    output = event["data"].get("output")
                    if output:
                        # Silently skip outputs that are internal framework Commands
                        if (
                            "Command(" in str(output)
                            or hasattr(output, "update")
                            or hasattr(output, "goto")
                        ):
                            continue

                        # Extract content from ToolMessage or raw list/dict
                        raw_content = getattr(output, "content", output)

                        # Handle list of content blocks
                        if isinstance(raw_content, list):
                            text_parts = []
                            for part in raw_content:
                                if (
                                    isinstance(part, dict)
                                    and part.get("type") == "text"
                                ):
                                    text_parts.append(part.get("text", ""))
                                elif isinstance(part, str):
                                    text_parts.append(part)
                            raw_content = "\n".join(text_parts)

                        # If content is still not a string, or is a JSON string, try to make it pretty
                        if not isinstance(raw_content, str):
                            try:
                                display_content = json.dumps(raw_content, indent=2)
                            except:
                                display_content = str(raw_content)
                        else:
                            try:
                                stripped = raw_content.strip()
                                if (
                                    stripped.startswith("{") and stripped.endswith("}")
                                ) or (
                                    stripped.startswith("[") and stripped.endswith("]")
                                ):
                                    parsed = json.loads(stripped)
                                    display_content = json.dumps(parsed, indent=2)
                                    display_content = f"```json\n{display_content}\n```"
                                else:
                                    display_content = raw_content
                            except:
                                display_content = raw_content

                        yield json.dumps(
                            {
                                "type": "tool_result",
                                "tool": tool_name,
                                "content": display_content,
                            }
                        ) + "\n"

        except Exception as e:
            logger.error(f"Error in astream_events: {e}", exc_info=True)
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
