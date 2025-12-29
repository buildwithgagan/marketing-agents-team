from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from .agent import agent_manager
from .investigator.graph import build_investigator_graph
from .utils import get_model_config
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import json
from contextlib import asynccontextmanager
import os
import logging
from typing import Optional, Dict, List
import asyncio
import sys
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger("deepagent-api")
DEBUG_EVENTS = os.getenv("DEEPAGENT_DEBUG_EVENTS", "").strip() == "1"
logger.setLevel(logging.DEBUG if DEBUG_EVENTS else logging.INFO)

# Global State for Investigator Event Queues
# thread_id -> asyncio.Queue
investigator_event_queues: Dict[str, asyncio.Queue] = {}

APPROVAL_KEYWORDS = {
    "approve",
    "approved",
    "ok",
    "okay",
    "yes",
    "go",
    "proceed",
}
FEEDBACK_HINTS = {
    "feedback",
    "modify",
    "change",
    "adjust",
    "improve",
    "expand",
    "revise",
    "add",
    "focus",
}


def detect_investigator_intent(feedback_text: Optional[str]) -> Optional[str]:
    if not feedback_text:
        return None
    text = feedback_text.lower().strip()
    if not text:
        return None
    if text in APPROVAL_KEYWORDS:
        return "approve"
    if any(hint in text for hint in FEEDBACK_HINTS):
        return "feedback"
    # If the feedback is longer than a short approval word, assume it is actual feedback
    if len(text.split()) > 3:
        return "feedback"
    return None


def chunk_text_for_stream(text: str, max_length: int = 1200) -> List[str]:
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks: List[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_length:
            chunks.append(paragraph)
            continue
        start = 0
        while start < len(paragraph):
            end = min(start + max_length, len(paragraph))
            chunk = paragraph[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end
    return chunks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Agent Manager...")
    await agent_manager.initialize()
    logger.info("Agent Manager initialized.")

    # Initialize Investigator Graph Persistence
    # Switch back to AsyncSqliteSaver
    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        app.state.investigator_checkpointer = checkpointer
        app.state.investigator_graph = build_investigator_graph(checkpointer)
        logger.info("Investigator Graph initialized with SQLite persistence.")

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

# --- Chat Endpoint (Brew Mode) ---


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
    investigator_action = data.get("investigator_action")  # "approve" or None
    investigator_thread = data.get("investigator_thread")  # thread_id for investigator
    investigator_feedback = data.get("investigator_feedback", "Approved")
    investigator_intent = data.get("investigator_intent")

    # Convert messages to LangChain BaseMessage format
    langchain_messages = []
    user_input = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract text from content array
            text_content = ""
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_content += item.get("text", "")
                elif isinstance(item, str):
                    text_content += item
            content = text_content
        elif not isinstance(content, str):
            content = str(content)

        # Extract user input from last user message for logging
        if role == "user":
            langchain_messages.append(HumanMessage(content=content))
            user_input = content  # Keep last user message for logging
        elif role == "assistant":
            langchain_messages.append(AIMessage(content=content))
        elif role == "system":
            langchain_messages.append(SystemMessage(content=content))

    # Determine effective mode
    effective_mode = mode if mode else "brew"

    effective_intent = investigator_intent or detect_investigator_intent(
        investigator_feedback
    )

    # Handle investigator resume/approval flow
    # But first check if this looks like a new investigation (not feedback)
    if investigator_thread:
        try:
            base_config = {"configurable": {"thread_id": investigator_thread}}
            state = await app.state.investigator_graph.aget_state(base_config)

            if not state or not state.values.get("research_plan"):
                logger.info(
                    f"Thread {investigator_thread} doesn't exist or has no plan. Starting new investigation."
                )
                investigator_thread = None
                investigator_feedback = None
                effective_intent = None
            else:
                if effective_intent == "feedback":
                    logger.info(
                        f"Investigator thread {investigator_thread} received feedback: {investigator_feedback}"
                    )
                    return await handle_investigator_feedback_stream(
                        investigator_thread,
                        investigator_feedback,
                        model_name,
                        thinking_enabled,
                    )
                logger.info(
                    f"Resuming investigator thread: {investigator_thread} with feedback: {investigator_feedback}"
                )
                return await handle_investigator_approval_stream(
                    investigator_thread,
                    investigator_feedback,
                    model_name,
                    thinking_enabled,
                )
        except Exception as e:
            logger.warning(
                f"Error checking thread state: {e}. Starting new investigation."
            )
            investigator_thread = None
            investigator_feedback = None
            effective_intent = None

    # Check if this is a new investigator command
    is_investigator_command = False
    investigator_topic = ""

    if user_input:
        lower_input = user_input.lower().strip()
        # Check for investigator commands via prefix
        if lower_input.startswith("investigate:") or lower_input.startswith(
            "/investigate"
        ):
            is_investigator_command = True
            # Extract topic
            if lower_input.startswith("investigate:"):
                investigator_topic = user_input[len("investigate:") :].strip()
            else:  # /investigate
                investigator_topic = user_input[len("/investigate") :].strip()
        # If mode is explicitly set to investigator, treat input as topic
        elif effective_mode == "investigator":
            is_investigator_command = True
            investigator_topic = user_input

    # Handle investigator start
    if is_investigator_command and investigator_topic:
        logger.info(f"Starting investigator for topic: {investigator_topic}")
        return await handle_investigator_start_stream(
            investigator_topic, model_name, thinking_enabled
        )

    # Regular chat mode
    if effective_mode not in ["brew"]:
        effective_mode = "brew"

    # Prepare inputs - Brew expects BaseMessage objects
    inputs = {"messages": langchain_messages}

    # Prepare configuration using shared helper
    config = get_model_config(thread_id, model_name, thinking_enabled, effective_mode)

    logger.info(
        f"User Query (Thread: {thread_id}, Mode: {effective_mode}, Model: {model_name}, Thinking: {thinking_enabled}): {user_input}"
    )

    agent = agent_manager.get_agent(effective_mode)

    async def event_generator():
        try:
            async for event in agent.astream_events(
                inputs, config=config, version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")

                # Handle streaming tokens
                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk:
                        # Handle thinking/reasoning content if present
                        attr_thought = (
                            getattr(chunk, "reasoning_content", None)
                            or chunk.additional_kwargs.get("reasoning_content")
                            or chunk.additional_kwargs.get("thought")
                            or chunk.additional_kwargs.get("thinking")
                        )

                        if attr_thought:
                            yield json.dumps(
                                {"type": "thought", "content": attr_thought}
                            ) + "\n"

                        # Handle standard content
                        content = chunk.content
                        if content:
                            if isinstance(content, str):
                                yield json.dumps(
                                    {"type": "content", "content": content}
                                ) + "\n"
                            elif isinstance(content, list):
                                # Handle list-based content (e.g., Responses API)
                                for item in content:
                                    if (
                                        isinstance(item, dict)
                                        and item.get("type") == "text"
                                    ):
                                        yield json.dumps(
                                            {
                                                "type": "content",
                                                "content": item.get("text", ""),
                                            }
                                        ) + "\n"

                # Handle final response from chain end (for non-streaming models or final output)
                elif kind == "on_chain_end" and name == "agent":
                    output = event["data"].get("output", {})
                    if output and "messages" in output:
                        # Extract the last AI message
                        for msg in output["messages"]:
                            if hasattr(msg, "content") and msg.content:
                                content = msg.content
                                if isinstance(content, str) and content:
                                    yield json.dumps(
                                        {"type": "content", "content": content}
                                    ) + "\n"
                                elif isinstance(content, list):
                                    for item in content:
                                        if (
                                            isinstance(item, dict)
                                            and item.get("type") == "text"
                                        ):
                                            yield json.dumps(
                                                {
                                                    "type": "content",
                                                    "content": item.get("text", ""),
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
            "X-Accel-Buffering": "no",
        },
    )


# --- Investigator Streaming Handlers for Chat ---


async def handle_investigator_start_stream(
    topic: str, model_name: str, thinking_enabled: bool
):
    """Start investigator and stream the research plan back to chat."""
    inv_thread_id = str(uuid.uuid4())
    config = get_model_config(
        inv_thread_id, model_name, thinking_enabled, "investigator"
    )

    initial_state = {
        "topic": topic,
        "model_name": model_name,
        "thinking_enabled": thinking_enabled,
    }

    async def event_generator():
        try:
            # Send initial status
            yield json.dumps(
                {
                    "type": "investigator_start",
                    "content": f"🔍 Starting research on: **{topic}**\n\nGenerating research plan...",
                }
            ) + "\n"

            # Run planner node (will stop at interrupt)
            await app.state.investigator_graph.ainvoke(initial_state, config)

            # Get the plan
            state = await app.state.investigator_graph.aget_state(config)
            plan = state.values.get("research_plan", {})

            # Stream the plan as a special message type
            yield json.dumps(
                {
                    "type": "investigator_plan",
                    "thread_id": inv_thread_id,
                    "plan": plan,
                    "content": "## 📋 Research Plan Generated\n\nPlease review and approve to continue.",
                }
            ) + "\n"

        except Exception as e:
            logger.error(f"Error starting investigator: {e}", exc_info=True)
            yield json.dumps(
                {"type": "error", "content": f"Error starting research: {str(e)}"}
            ) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def handle_investigator_feedback_stream(
    inv_thread_id: str, feedback: str, model_name: str, thinking_enabled: bool
):
    """Re-run the planner after user feedback to produce an updated plan."""
    base_config = {"configurable": {"thread_id": inv_thread_id}}

    # Check if thread exists
    state = await app.state.investigator_graph.aget_state(base_config)
    if not state:

        async def error_gen():
            yield json.dumps(
                {
                    "type": "error",
                    "content": "Investigator thread not found. Please start a new investigation.",
                }
            ) + "\n"

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    stored_topic = state.values.get("topic")
    stored_model = state.values.get("model_name", model_name)
    stored_thinking = state.values.get("thinking_enabled", thinking_enabled)

    if not stored_topic:

        async def error_gen():
            yield json.dumps(
                {
                    "type": "error",
                    "content": "Investigator thread state missing topic. Please start a new investigation.",
                }
            ) + "\n"

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # Reconstruct config
    config = get_model_config(
        inv_thread_id, stored_model, stored_thinking, "investigator"
    )

    initial_state = {
        "topic": stored_topic,
        "model_name": stored_model,
        "thinking_enabled": stored_thinking,
        "user_feedback": feedback,
    }

    async def event_generator():
        try:
            yield json.dumps(
                {
                    "type": "investigator_status",
                    "content": "📝 Feedback received. Updating research plan...",
                }
            ) + "\n"

            await app.state.investigator_graph.ainvoke(initial_state, config)

            state = await app.state.investigator_graph.aget_state(config)
            plan = state.values.get("research_plan", {})
            yield json.dumps(
                {
                    "type": "investigator_plan",
                    "thread_id": inv_thread_id,
                    "plan": plan,
                    "content": "## 📋 Research Plan Updated\n\nPlease review and approve to continue.",
                }
            ) + "\n"

        except Exception as e:
            logger.error(f"Error updating investigator plan: {e}", exc_info=True)
            yield json.dumps(
                {"type": "error", "content": f"Error updating plan: {str(e)}"}
            ) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def handle_investigator_approval_stream(
    inv_thread_id: str, feedback: str, model_name: str, thinking_enabled: bool
):
    """Handle approval and stream execution results."""
    base_config = {"configurable": {"thread_id": inv_thread_id}}

    # Check if thread exists
    state = await app.state.investigator_graph.aget_state(base_config)
    if not state:

        async def error_gen():
            yield json.dumps(
                {
                    "type": "error",
                    "content": "Investigator thread not found. Please start a new investigation.",
                }
            ) + "\n"

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # Get stored model config and topic
    stored_model = state.values.get("model_name", model_name)
    stored_thinking = state.values.get("thinking_enabled", thinking_enabled)
    stored_topic = state.values.get("topic")

    # If topic is missing, this is a corrupted state - return error
    if not stored_topic:

        async def error_gen():
            yield json.dumps(
                {
                    "type": "error",
                    "content": "Investigator thread state is invalid (missing topic). Please start a new investigation.",
                }
            ) + "\n"

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # Reconstruct config
    config = get_model_config(
        inv_thread_id, stored_model, stored_thinking, "investigator"
    )

    # Update with feedback - preserve topic and other state values
    # Specify as_node since graph is interrupted after planner
    await app.state.investigator_graph.aupdate_state(
        base_config,
        {
            "user_feedback": feedback,
            "topic": stored_topic,  # Preserve topic
        },
        as_node="planner",
    )

    async def event_generator():
        try:
            yield json.dumps(
                {
                    "type": "investigator_status",
                    "content": "✅ Plan approved! Starting research execution...",
                }
            ) + "\n"

            # Stream execution events
            async for event in app.state.investigator_graph.astream_events(
                None, config, version="v1"
            ):
                kind = event["event"]
                name = event.get("name", "")

                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk:
                        content = chunk.content
                        if content:
                            if isinstance(content, str):
                                yield json.dumps(
                                    {"type": "content", "content": content}
                                ) + "\n"

                elif kind == "on_tool_start":
                    tool_input = event["data"].get("input", {})
                    tool_name = name or "tool"
                    input_str = str(
                        tool_input.get(
                            "query",
                            tool_input.get("url", tool_input.get("keywords", "")),
                        )
                    )
                    yield json.dumps(
                        {
                            "type": "investigator_status",
                            "content": f"🔍 Running {tool_name}... {input_str[:50] if input_str else ''}",
                        }
                    ) + "\n"

                elif kind == "on_tool_end":
                    yield json.dumps(
                        {
                            "type": "investigator_status",
                            "content": f"✅ {name or 'Tool'} completed",
                        }
                    ) + "\n"

                elif kind == "on_chain_end":
                    output = event["data"].get("output", {})

                    if name == "reporter" and output and "final_report" in output:
                        report_chunks = chunk_text_for_stream(output["final_report"])
                        if not report_chunks:
                            report_chunks = [""]
                        for idx, chunk in enumerate(report_chunks, start=1):
                            yield json.dumps(
                                {
                                    "type": "investigator_report",
                                    "chunk_index": idx,
                                    "chunk_total": len(report_chunks),
                                    "content": chunk,
                                }
                            ) + "\n"
                    elif name == "executor":
                        yield json.dumps(
                            {
                                "type": "investigator_status",
                                "content": "📊 Data gathering complete, generating report...",
                            }
                        ) + "\n"

            yield json.dumps(
                {"type": "investigator_complete", "content": "✅ Research complete!"}
            ) + "\n"

        except Exception as e:
            logger.error(f"Error in investigator execution: {e}", exc_info=True)
            yield json.dumps(
                {"type": "error", "content": f"Error during research: {str(e)}"}
            ) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Investigator Agent Endpoints ---


class StartRequest(BaseModel):
    topic: str
    model: Optional[str] = "gpt-4.1"
    thinking: Optional[bool] = False


class ApproveRequest(BaseModel):
    thread_id: str
    feedback: str


async def run_investigator_stream(graph, config, input_data=None):
    """
    Runs the investigator graph and publishes events to the thread's event queue.
    """
    thread_id = config["configurable"]["thread_id"]
    queue = investigator_event_queues.get(thread_id)

    if not queue:
        logger.warning(
            f"No listener for thread {thread_id}, skipping stream publishing."
        )
        return

    try:
        async for event in graph.astream_events(input_data, config, version="v1"):
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk:
                    # Handle content
                    content = chunk.content
                    if content:
                        if isinstance(content, str):
                            await queue.put(
                                json.dumps({"type": "token", "content": content})
                            )
                        elif isinstance(content, list):
                            for item in content:
                                if (
                                    isinstance(item, dict)
                                    and item.get("type") == "text"
                                ):
                                    await queue.put(
                                        json.dumps(
                                            {
                                                "type": "token",
                                                "content": item.get("text", ""),
                                            }
                                        )
                                    )

            elif kind == "on_tool_start":
                tool_input = event["data"].get("input", {})
                tool_name = name or "tool"
                input_str = str(
                    tool_input.get(
                        "query", tool_input.get("url", tool_input.get("keywords", ""))
                    )
                )
                await queue.put(
                    json.dumps(
                        {
                            "type": "status",
                            "content": f"🔍 Running {tool_name}... {input_str[:50] if input_str else ''}",
                        }
                    )
                )

            elif kind == "on_tool_end":
                await queue.put(
                    json.dumps(
                        {"type": "status", "content": f"✅ {name or 'Tool'} completed"}
                    )
                )

            elif kind == "on_chain_end":
                output = event["data"].get("output", {})

                # Handle reporter node final output
                if name == "reporter" and output and "final_report" in output:
                    await queue.put(
                        json.dumps(
                            {"type": "report", "content": output["final_report"]}
                        )
                    )
                # Handle executor node completion
                elif name == "executor":
                    await queue.put(
                        json.dumps(
                            {
                                "type": "status",
                                "content": "📊 Data gathering complete, generating report...",
                            }
                        )
                    )
                # Handle planner node completion
                elif name == "planner":
                    await queue.put(
                        json.dumps(
                            {"type": "status", "content": "✅ Research plan generated"}
                        )
                    )

        await queue.put(json.dumps({"type": "complete"}))

    except Exception as e:
        logger.error(f"Error in background run: {e}")
        await queue.put(json.dumps({"type": "error", "content": str(e)}))


@app.post("/start")
async def start_research(req: StartRequest):
    """
    Starts the graph thread. Runs Planner -> Interrupt.
    Returns thread_id and plan.
    """
    thread_id = str(uuid.uuid4())

    # Use shared config helper
    config = get_model_config(thread_id, req.model, req.thinking, "investigator")

    logger.info(f"Starting research for topic: {req.topic} (Model: {req.model})")

    # Store model config in initial state so we can retrieve it later
    initial_state = {
        "topic": req.topic,
        "model_name": req.model,
        "thinking_enabled": req.thinking,
    }

    # Run until interrupt (Planner -> Executor [Interrupt])
    await app.state.investigator_graph.ainvoke(initial_state, config)

    # Fetch state to get the plan
    state = await app.state.investigator_graph.aget_state(config)
    plan = state.values.get("research_plan", {})

    return {"thread_id": thread_id, "research_plan": plan}


@app.post("/approve")
async def approve_plan(req: ApproveRequest, background_tasks: BackgroundTasks):
    """
    Approves the plan and resumes execution.
    """
    thread_id = req.thread_id

    # Check if thread exists and retrieve stored model config
    base_config = {"configurable": {"thread_id": thread_id}}
    state = await app.state.investigator_graph.aget_state(base_config)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Retrieve model config from state (stored during /start)
    stored_model = state.values.get("model_name", "gpt-4.1")
    stored_thinking = state.values.get("thinking_enabled", False)

    # Reconstruct full config with model settings
    config = get_model_config(thread_id, stored_model, stored_thinking, "investigator")

    # Update state with feedback
    logger.info(
        f"Approving thread {thread_id} with feedback: {req.feedback} (Model: {stored_model})"
    )
    await app.state.investigator_graph.aupdate_state(
        base_config, {"user_feedback": req.feedback}
    )

    # Initialize queue if needed (though stream endpoint should have done it)
    if thread_id not in investigator_event_queues:
        investigator_event_queues[thread_id] = asyncio.Queue()

    # Resume execution in background with proper config
    background_tasks.add_task(
        run_investigator_stream, app.state.investigator_graph, config, None
    )

    return {"status": "approved", "message": "Research execution resumed."}


@app.get("/stream/{thread_id}")
async def stream_events(thread_id: str):
    """
    SSE Endpoint for real-time updates.
    """
    logger.info(f"Client connected to stream for {thread_id}")

    if thread_id not in investigator_event_queues:
        investigator_event_queues[thread_id] = asyncio.Queue()

    queue = investigator_event_queues[thread_id]

    async def event_generator():
        try:
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"

                try:
                    parsed = json.loads(data)
                    if parsed.get("type") in ["complete", "error"]:
                        break
                except:
                    pass
        except asyncio.CancelledError:
            logger.info(f"Stream disconnected for {thread_id}")
            # Optional cleanup logic here

    return StreamingResponse(event_generator(), media_type="text/event-stream")
