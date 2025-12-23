import os
import asyncio
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import MemorySaver

# Load env variables
load_dotenv()

class AgentManager:
    def __init__(self):
        self.client = None
        self.session_context = None
        self.session = None
        self.agent = None
        self.checkpointer = MemorySaver()

    async def initialize(self):
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise ValueError("TAVILY_API_KEY not found in environment.")

        mcp_url = f"https://mcp.tavily.com/mcp?tavilyApiKey={tavily_api_key}"
        print(f"Connecting to Tavily MCP via 'npx mcp-remote' bridge...")

        self.client = MultiServerMCPClient(
            {
                "tavily": {
                    "command": "npx",
                    "args": ["-y", "mcp-remote", mcp_url],
                    "transport": "stdio"
                }
            }
        )
        
        self.session_context = self.client.session("tavily")
        self.session = await self.session_context.__aenter__()
        
        print("Session established. Loading tools...")
        tavily_tools = await load_mcp_tools(self.session)
        print(f"Loaded {len(tavily_tools)} tools from Tavily: {[t.name for t in tavily_tools]}")

        # Configure Model
        model = ChatOpenAI(model="gpt-4.1", temperature=0)

        # Configure Subagents
        research_agent = {
            "name": "research-agent",
            "description": "Specialized agent for deep research tasks, market analysis, and broad topic exploration.",
            "model": "gpt-4.1", 
            "tools": tavily_tools, 
            "system_prompt": "You are a specialized Research Agent. Use 'tavily-search' to find information and 'tavily-extract' to get content from key sources. Synthesize your findings into a comprehensive answer."
        }

        crawl_agent = {
            "name": "crawl-agent",
            "description": "Specialized agent for crawling websites and extracting structured data.",
            "model": "gpt-4.1",
            "tools": tavily_tools,
            "system_prompt": "You are a specialized Crawl Agent. Use 'tavily-crawl' to explore websites and 'tavily-extract' (or 'tavily-map') to gather data. Focus on structure and completeness."
        }

        subagents = [research_agent, crawl_agent]

        system_prompt = """You are a helpful Deep Agent powered by Tavily MCP and DeepAgents framework.
        
        Your Capabilities:
        1. **Planning**: Always start by writing a plan (todos) for complex requests.
        2. **Real-time Knowledge**: Use the `research-agent` or direct tools (`tavily-search`) to get the latest news and information.
        3. **Web Crawling**: Use the `crawl-agent` to map and extract data from specific websites.
        4. **File System**: You can read/write files to save your reports or code.
        
        If the user asks about the latest news, use your tools or the research sub-agent.
        If the user asks to crawl a site, delegate to the crawl sub-agent.
        """

        from deepagents import create_deep_agent
        self.agent = create_deep_agent(
            model=model,
            tools=tavily_tools,
            subagents=subagents,
            system_prompt=system_prompt,
            checkpointer=self.checkpointer
        )
        print("Agent initialized successfully.")

    async def cleanup(self):
        if self.session_context:
            await self.session_context.__aexit__(None, None, None)
            print("MCP session closed.")

agent_manager = AgentManager()
