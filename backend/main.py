import asyncio
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from deepagents import create_deep_agent

load_dotenv()

import asyncio
import os
import sys
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from deepagents import create_deep_agent

load_dotenv()

async def main():
    # 1. Load API Keys
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        print("Error: TAVILY_API_KEY not found in .env. Please add it.")
        return

    mcp_url = f"https://mcp.tavily.com/mcp?tavilyApiKey={tavily_api_key}" # remote url for mcp-remote
    
    print(f"Connecting to Tavily MCP via 'npx mcp-remote' bridge...")

    try:
        # Initialize the client using stdio transport with mcp-remote
        # This bridges the local stdio connection to the remote SSE server
        client = MultiServerMCPClient(
            {
                "tavily": {
                    "command": "npx",
                    "args": ["-y", "mcp-remote", mcp_url],
                    "transport": "stdio"
                }
            }
        )
            
        print("MCP Client initialized. Opening session...")
        
        # Open a session to the Tavily server. 
        # We must keep this session open for the tools to work.
        async with client.session("tavily") as session:
            print("Session established.")
            tavily_tools = await load_mcp_tools(session)
            print(f"Loaded {len(tavily_tools)} tools from Tavily: {[t.name for t in tavily_tools]}")

            # 3. Configure Model
            # Using GPT-4.1 as the brain
            model = ChatOpenAI(model="gpt-4.1", temperature=0)

            # 4. Configure Subagents
            # Research Agent: Uses search and extract to synthesis information
            research_agent = {
                "name": "research-agent",
                "description": "Specialized agent for deep research tasks, market analysis, and broad topic exploration.",
                "model": "gpt-4.1-mini", 
                "tools": tavily_tools, 
                "system_prompt": "You are a specialized Research Agent. Use 'tavily-search' to find information and 'tavily-extract' to get content from key sources. Synthesize your findings into a comprehensive answer."
            }

            # Crawl Agent: Uses crawl and extract for site-specific data
            crawl_agent = {
                "name": "crawl-agent",
                "description": "Specialized agent for crawling websites and extracting structured data.",
                "model": "gpt-4.1-mini",
                "tools": tavily_tools,
                "system_prompt": "You are a specialized Crawl Agent. Use 'tavily-crawl' to explore websites and 'tavily-extract' (or 'tavily-map') to gather data. Focus on structure and completeness."
            }

            subagents = [research_agent, crawl_agent]

            # 5. Create Deep Agent
            # The create_deep_agent function automatically adds built-in middleware:
            # - TodoListMiddleware (Planning)
            # - FilesystemMiddleware (File I/O)
            # - SubAgentMiddleware (Delegation)
            # - SummarizationMiddleware (Context management)
            
            system_prompt = """You are a helpful Deep Agent powered by Tavily MCP and DeepAgents framework.
            
            Your Capabilities:
            1. **Planning**: Always start by writing a plan (todos) for complex requests.
            2. **Real-time Knowledge**: Use the `research-agent` or direct tools (`tavily-search`) to get the latest news and information.
            3. **Web Crawling**: Use the `crawl-agent` to map and extract data from specific websites.
            4. **File System**: You can read/write files to save your reports or code.
            
            If the user asks about the latest news, use your tools or the research sub-agent.
            If the user asks to crawl a site, delegate to the crawl sub-agent.
            """

            agent = create_deep_agent(
                model=model,
                tools=tavily_tools, # Give main agent tools too for quick lookups
                subagents=subagents,
                system_prompt=system_prompt,
            )

            # 6. Interactive Loop
            print("\n🚀 Deep Agent Ready! (Type 'quit' to exit)")
            print("Try asking: 'Research the latest developments in AI Agents' or 'Crawl python.org'")
            
            while True:
                try:
                    user_input = input("\nUser (DeepAgent)> ")
                    if user_input.lower() in ["quit", "exit", "q"]:
                        break
                    if not user_input.strip():
                        continue
                    
                    inputs = {"messages": [{"role": "user", "content": user_input}]}
                    
                    # specific to LangGraph streaming
                    try:
                        async for chunk in agent.astream(inputs, stream_mode="updates"):
                            for node, value in chunk.items():
                                # Filter out internal middleware noise
                                if node in ["PatchToolCallsMiddleware.before_agent", "SummarizationMiddleware.before_model"]:
                                    continue
                                
                                # Handle standard dictionary updates with messages
                                if isinstance(value, dict) and "messages" in value:
                                    # It might be a list or a single message (depending on graph state)
                                    msgs = value["messages"]
                                    if isinstance(msgs, list) and msgs:
                                        last_msg = msgs[-1]
                                        print(f"\n[{node}]: {last_msg.content}")
                                    else:
                                        # Fallback for unexpected structure
                                        print(f"\n[{node}]: {msgs}")
                                else:
                                    # Print other updates (like tools returning direct strings)
                                    print(f"\n[{node}]: {value}")
                                    
                    except Exception as inner_e:
                        print(f"Error during streaming: {inner_e}")
                        # import traceback
                        # traceback.print_exc() (Keep hidden unless debugging)

                except KeyboardInterrupt:
                    print("\nUser interrupted. Exiting loop.")
                    break
                except Exception as loop_error:
                    print(f"Error in conversation loop: {loop_error}")
                    import traceback
                    traceback.print_exc()

    except Exception as e:
        print(f"\nCRITICAL ERROR: Could not connect to MCP or initialize agent.\nDetails: {e}")
        print("Please check your TAVILY_API_KEY and internet connection.")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


