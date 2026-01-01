import asyncio
import json
import logging
import uuid
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agent import agent_manager

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# Global Event Queues
event_queues: Dict[str, asyncio.Queue] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Agent Manager (loads all graphs)
    await agent_manager.initialize()
    logger.info("Agent Manager Initialized")
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
    model: str = "gpt-5-mini"
    mode: str = "investigator"


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
                    # --- Investigator Events ---
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
                    elif name == "reporter":
                        await queue.put(
                            json.dumps(
                                {"type": "report", "content": output.get("final_report")}
                            )
                        )
                    
                    # --- Omniscient Events ---
                    # elif name == "chief_editor":
                    #      await queue.put(
                    #         json.dumps(
                    #             {"type": "status", "content": f"📚 Outline generated with {len(output.get('book_outline', []))} chapters."}
                    #         )
                    #     )
                    # elif name == "writer":
                    #      idx = output.get("current_chapter_index", 0)
                    #      await queue.put(
                    #         json.dumps(
                    #             {"type": "status", "content": f"✍️ Finished drafting Chapter {idx}."}
                    #         )
                    #     )
                    # elif name == "assembler":
                    #      # The assembler returns 'messages' with the full report as the last message content?
                    #      # Or we look at what 'assembler_node' returned.
                    #      # It returned {"messages": [HumanMessage(content=full_report)], "status": "complete"}
                    #      # Wait, 'on_chain_end' for a node returns the node's output.
                    #      msgs = output.get("messages", [])
                    #      if msgs:
                    #          report_content = msgs[0].content if hasattr(msgs[0], "content") else str(msgs[0])
                    #          await queue.put(
                    #             json.dumps({"type": "report", "content": report_content})
                    #         )

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

    config = {
        "configurable": {
            "thread_id": thread_id,
            "model_name": req.model,
            "output_version": "responses/v1",
        }
    }

    event_queues[thread_id] = asyncio.Queue()
    logger.info(f"Starting {thread_id} for {req.topic} (Mode: {req.mode})")

    try:
        agent = agent_manager.get_agent(req.mode)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Async invoke to start the graph
    # For Omniscient, we assume it runs fully or until interrupt
    # Investigator interrupts at planner.
    await agent.ainvoke({"topic": req.topic}, config)
    
    # Check state for immediate results (Investigator Planner)
    state = await agent.aget_state(config)
    
    response = {"thread_id": thread_id}
    
    if req.mode == "investigator":
        plan = state.values.get("research_plan")
        response["plan"] = plan
    
    # Add background task to stream subsequent events if it's meant to run autonomously?
    # Actually, the client is expected to connect to /stream right after. 
    # But for Investigator, it pauses.
    # For Omniscient, it runs fully. 
    # If we 'await ainvoke', it waits until the end (Omniscient) or interrupt (Investigator).
    # If Omniscient runs for 15 mins, 'await ainvoke' will timeout the HTTP request!
    # We should use `ainvoke` in background for Omniscient?
    # Or just return thread_id and let /stream pick it up? 
    # LangGraph's ainvoke waits.
    
    # FIX: For long running modes (Omniscient), we should NOT await result in the endpoint.
    # But for Investigator, we need the initial plan to return in the JSON response?
    # Current Investigator flow:
    # 1. /start (waits for ainvoke to hit interrupt at planner) -> returns Plan
    # 2. Client shows plan.
    
    # Omniscient flow:
    # 1. /start (should kick off background task?) -> returns thread_id
    # 2. Client listens to stream.
    
    # If I await ainvoke for Omniscient, it will timeout.
    # So I must run it in background IF mode != investigator? 
    # Or always background and client relies on stream?
    # The current 'test_investigator' expects 'plan' in /start response.
    
    # if req.mode == "omniscient":
    #     # Run in background
    #      asyncio.create_task(
    #         stream_graph_execution(agent, config, {"topic": req.topic}, thread_id)
    #     )
         # We don't return plan for Omniscient in response, client gets it via Status stream
    
    return response


@app.post("/approve")
async def approve_plan(req: ApproveRequest, tasks: BackgroundTasks):
    config = {"configurable": {"thread_id": req.thread_id}}

    # We assume this is for Investigator mode since it's "Plan Approval"
    agent = agent_manager.get_agent("investigator")

    state = await agent.aget_state(config)
    if not state or "topic" not in state.values:
        logger.error(f"State missing 'topic' for thread {req.thread_id}")
        return {"status": "error", "message": "State missing required 'topic' field"}

    await agent.aupdate_state(config, {"user_feedback": req.feedback})
    
    if req.thread_id not in event_queues:
        event_queues[req.thread_id] = asyncio.Queue()

    tasks.add_task(
        stream_graph_execution, agent, config, {}, req.thread_id
    )

    return {"status": "started", "message": "Listen to /stream/{thread_id}"}


@app.get("/stream/{thread_id}")
async def stream_events(thread_id: str):
    if thread_id not in event_queues:
        event_queues[thread_id] = asyncio.Queue()
    queue = event_queues[thread_id]

    async def event_generator():
        while True:
            try:
                # Wait for data with a timeout to allow checking connection status
                data = await asyncio.wait_for(queue.get(), timeout=1.0)
                if data:
                    yield f"data: {data}\n\n"
                    # If we sent a complete message, we can stop
                    payload = json.loads(data)
                    if payload.get("type") == "complete":
                        break
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
            except Exception as e:
                logger.error(f"Queue error: {e}")
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")

