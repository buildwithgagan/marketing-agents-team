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
    model_name = data.get("model", "gpt-4.1")
    thinking_enabled = data.get("thinking", False)
    
    last_message = messages[-1] if messages else {"content": ""}
    user_input = last_message.get("content", "")

    # We only send the latest message because the agent uses the checkpointer to remember history
    inputs = {"messages": [{"role": "user", "content": user_input}]}
    config = {
        "configurable": {
            "thread_id": thread_id,
            "model_name": model_name,
            "thinking": thinking_enabled
        }
    }
    
    logger.info(f"User Query (Thread: {thread_id}, Model: {model_name}, Thinking: {thinking_enabled}): {user_input}")

    async def event_generator():
        try:
            async for event in agent_manager.agent.astream_events(inputs, config=config, version="v2"):
                kind = event["event"]
                name = event.get("name", "")
                
                # Todo List / Planning updates
                if kind == "on_chain_end" and name == "TodoListMiddleware":
                    output = event["data"].get("output")
                    if output and isinstance(output, dict) and "todo_list" in output:
                        todo_data = output["todo_list"]
                        # Extract list if it's the Perplexity-style {todos: [...]} object
                        if isinstance(todo_data, dict) and "todos" in todo_data:
                            todo_data = todo_data["todos"]
                        
                        # Final safety: If it's still not a list, make it one
                        if not isinstance(todo_data, list):
                            todo_data = [str(todo_data)]
                        
                        yield json.dumps({"type": "plan", "content": todo_data}) + "\n"

                # Token streaming
                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk:
                        content = getattr(chunk, "content", "")
                        if content:
                            yield json.dumps({"type": "content", "content": content}) + "\n"
                
                # Node transition / Status updates
                elif kind == "on_chain_start":
                    if name in ["research-agent", "crawl-agent", "master-agent", "agent"]:
                        status_map = {
                            "research-agent": "Deep researching using Tavily...",
                            "crawl-agent": "Crawling website data...",
                            "master-agent": "Master Orchestrator planning...",
                            "agent": "Thinking and planning...",
                        }
                        friendly_status = status_map.get(name, f"Processing: {name}")
                        yield json.dumps({"type": "status", "content": friendly_status}) + "\n"
                
                # Tool calls (Start)
                elif kind == "on_tool_start":
                    tool_name = name or "tool"
                    
                    # Filter out internal planning tools from the search progress UI
                    if tool_name in ["write_todos", "update_todos"]:
                        continue
                        
                    raw_input = event["data"].get("input", "")
                    
                    # Clean up input for the UI: Extract 'query' and remove 'runtime'/technical noise
                    tool_input = ""
                    if isinstance(raw_input, dict):
                        # Use 'query' if available, otherwise 'url', then fall back to full dict minus technical keys
                        tool_input = raw_input.get("query") or raw_input.get("url")
                        if not tool_input:
                            ui_input = {k: v for k, v in raw_input.items() if k not in ["runtime", "state"]}
                            tool_input = json.dumps(ui_input)
                    else:
                        tool_input = str(raw_input)
                    
                    # Truncate if too long for the search progress bubble
                    if len(tool_input) > 80:
                        tool_input = tool_input[:77] + "..."

                    logger.info(f"Tool Call Start: {tool_name} with {tool_input}")
                    yield json.dumps({
                        "type": "tool_start", 
                        "tool": tool_name, 
                        "content": f"Running {tool_name}...", 
                        "input": tool_input,
                        "tool_name": tool_name
                    }) + "\n"
                
                # Tool results (End)
                elif kind == "on_tool_end":
                    tool_name = name or "tool"
                    if tool_name in ["write_todos", "update_todos"]:
                        continue

                    output = event["data"].get("output")
                    if output:
                        # Silently skip outputs that are internal framework Commands
                        if "Command(" in str(output) or hasattr(output, "update") or hasattr(output, "goto"):
                             continue

                        # Extract content from ToolMessage or raw list/dict
                        raw_content = getattr(output, "content", output)
                        
                        # Handle list of content blocks
                        if isinstance(raw_content, list):
                            text_parts = []
                            for part in raw_content:
                                if isinstance(part, dict) and part.get("type") == "text":
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
                                if (stripped.startswith('{') and stripped.endswith('}')) or \
                                   (stripped.startswith('[') and stripped.endswith(']')):
                                    parsed = json.loads(stripped)
                                    display_content = json.dumps(parsed, indent=2)
                                    display_content = f"```json\n{display_content}\n```"
                                else:
                                    display_content = raw_content
                            except:
                                display_content = raw_content

                        yield json.dumps({
                            "type": "tool_result", 
                            "tool": tool_name,
                            "content": display_content 
                        }) + "\n"

        except Exception as e:
            logger.error(f"Error in astream_events: {e}", exc_info=True)
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
