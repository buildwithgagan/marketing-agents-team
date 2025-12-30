import asyncio
import json
import logging
import uuid
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from .investigator.graph import (
    build_executor_graph,
    build_investigator_graph,
)

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# Global Event Queues
event_queues: Dict[str, asyncio.Queue] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        app.state.graph = build_investigator_graph(checkpointer)
        logger.info("Graph Initialized")
        app.state.checkpointer = checkpointer
        yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartRequest(BaseModel):
    topic: str
    model: str = "gpt-4.1-mini"  # <--- UPDATED DEFAULT


class ApproveRequest(BaseModel):
    thread_id: str
    feedback: str = "Approved"


# --- Streaming Helper ---
async def stream_graph_execution(graph, config, input_data, thread_id):
    """
    Stream graph execution events.
    When input_data is {}, LangGraph continues from the checkpointed state.
    """
    queue = event_queues.get(thread_id)
    if not queue:
        return

    try:
        current_input = input_data
        
        while True:
            should_resume = False
            is_continuing = current_input == {}

            async for event in graph.astream_events(current_input, config, version="v1"):
                kind = event["event"]
                name = event.get("name", "")

                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    content = chunk.content if chunk else ""
                    if content:
                        await queue.put(json.dumps({"type": "token", "content": content}))

                elif kind == "on_tool_start":
                    t_name = name or "tool"
                    await queue.put(
                        json.dumps({"type": "status", "content": f"🛠️ Running {t_name}..."})
                    )

                elif kind == "on_chain_end":
                    output = event["data"].get("output", {})
                    if name == "planner":
                        if output.get("user_feedback") == "" and is_continuing:
                            await queue.put(json.dumps({"type": "approved"}))
                            should_resume = True
                        else:
                            await queue.put(
                                json.dumps(
                                    {"type": "plan", "content": output.get("research_plan")}
                                )
                            )
                    elif name == "executor":
                        pass
                    elif name == "reporter":
                        await queue.put(
                            json.dumps(
                                {"type": "report", "content": output.get("final_report")}
                            )
                        )
                elif kind == "on_chain_start":
                    if name == "executor":
                        await queue.put(
                            json.dumps(
                                {"type": "status", "content": "🚀 Starting execution..."}
                            )
                        )

            if should_resume:
                current_input = None
                await queue.put(json.dumps({"type": "status", "content": "🔄 Loading..."}))
                continue
            else:
                break

        await queue.put(json.dumps({"type": "complete"}))

    except Exception as e:
        logger.error(f"Stream error: {e}")
        await queue.put(json.dumps({"type": "error", "content": str(e)}))


# --- Endpoints ---


@app.post("/start")
async def start_research(req: StartRequest):
    thread_id = str(uuid.uuid4())

    # Pass response output version just in case
    config = {
        "configurable": {
            "thread_id": thread_id,
            "model_name": req.model,
            "output_version": "responses/v1",
        }
    }

    event_queues[thread_id] = asyncio.Queue()
    logger.info(f"Starting {thread_id} for {req.topic}")

    await app.state.graph.ainvoke({"topic": req.topic}, config)

    state = await app.state.graph.aget_state(config)
    plan = state.values.get("research_plan")

    return {"thread_id": thread_id, "plan": plan}


@app.post("/approve")
async def approve_plan(req: ApproveRequest, tasks: BackgroundTasks):
    config = {"configurable": {"thread_id": req.thread_id}}

    # Retrieve current state from checkpoint to verify required fields exist
    state = await app.state.graph.aget_state(config)
    if not state or "topic" not in state.values:
        logger.error(f"State missing 'topic' for thread {req.thread_id}")
        return {"status": "error", "message": "State missing required 'topic' field"}

    # Update state with user feedback
    await app.state.graph.aupdate_state(config, {"user_feedback": req.feedback})

    # Verify the state update was committed by retrieving state again
    updated_state = await app.state.graph.aget_state(config)
    if updated_state.values.get("user_feedback") != req.feedback:
        logger.warning(
            f"State update may not have been committed for thread {req.thread_id}"
        )

    if req.thread_id not in event_queues:
        event_queues[req.thread_id] = asyncio.Queue()

    # Build the full investigator graph.
    # The 'planner_node' inside will decide whether to proceed or regenerate based on feedback.
    # Using 'executor_graph' forces it to skip the planner entirely, which breaks modification requests.

    # Use the FULL investigator graph so we route back to Planner if needed
    investigator_graph = build_investigator_graph(app.state.checkpointer)
    tasks.add_task(
        stream_graph_execution, investigator_graph, config, {}, req.thread_id
    )

    return {"status": "started", "message": "Listen to /stream/{thread_id}"}


@app.get("/stream/{thread_id}")
async def stream_events(thread_id: str):
    if thread_id not in event_queues:
        event_queues[thread_id] = asyncio.Queue()
    queue = event_queues[thread_id]

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
            logger.info("Client disconnected")

    return StreamingResponse(event_generator(), media_type="text/event-stream")
