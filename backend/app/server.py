from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from .agent import agent_manager
import json
import asyncio
from contextlib import asynccontextmanager

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("deepagent-api")

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
    last_message = messages[-1] if messages else {"content": ""}
    user_input = last_message.get("content", "")

    # We only send the latest message because the agent uses the checkpointer to remember history
    inputs = {"messages": [{"role": "user", "content": user_input}]}
    config = {"configurable": {"thread_id": thread_id}}
    
    logger.info(f"User Query (Thread: {thread_id}): {user_input}")

    async def event_generator():
        try:
            async for event in agent_manager.agent.astream_events(inputs, config=config, version="v2"):
                kind = event["event"]
                
                # Token streaming
                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk:
                        content = getattr(chunk, "content", "")
                        if content:
                            yield json.dumps({"type": "content", "content": content}) + "\n"
                
                # Node transition / Status updates
                elif kind == "on_chain_start":
                    name = event.get("name", "")
                    if name in ["research-agent", "crawl-agent", "agent"]:
                        status_map = {
                            "research-agent": "Deep researching using Tavily...",
                            "crawl-agent": "Crawling website data...",
                            "agent": "Thinking and planning...",
                        }
                        friendly_status = status_map.get(name, f"Processing: {name}")
                        yield json.dumps({"type": "status", "content": friendly_status}) + "\n"
                
                # Tool calls
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    logger.info(f"Tool Call Start: {tool_name}")
                    yield json.dumps({"type": "status", "content": f"Running tool: {tool_name}..."}) + "\n"
                
                # Tool results
                elif kind == "on_tool_end":
                    output = event["data"].get("output")
                    if output:
                        # Extract content from ToolMessage or raw list/dict
                        content = getattr(output, "content", output)
                        
                        # Handle list of content blocks (common in recent LangChain/OpenAI versions)
                        if isinstance(content, list):
                            text_parts = []
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    text_parts.append(part.get("text", ""))
                                elif isinstance(part, str):
                                    text_parts.append(part)
                            content = "\n".join(text_parts)
                        
                        # If content is still not a string, or is a JSON string, try to make it pretty
                        if not isinstance(content, str):
                            content = json.dumps(content, indent=2)
                        else:
                            # If it's a string that looks like JSON, parse and re-format for readability
                            try:
                                stripped = content.strip()
                                if (stripped.startswith('{') and stripped.endswith('}')) or \
                                   (stripped.startswith('[') and stripped.endswith(']')):
                                    parsed = json.loads(stripped)
                                    content = json.dumps(parsed, indent=2)
                                    # Wrap in markdown code block for better rendering
                                    content = f"```json\n{content}\n```"
                            except:
                                pass

                        yield json.dumps({"type": "tool_result", "content": content}) + "\n"

        except Exception as e:
            logger.error(f"Error in astream_events: {e}", exc_info=True)
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
