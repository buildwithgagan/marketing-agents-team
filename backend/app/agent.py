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
            "description": "Expert in global discovery. Use this to find the best URLs and initial facts across the web.",
            "model": "gpt-4.1", 
            "tools": tavily_tools, 
            "system_prompt": "You are a Discovery Expert. Use 'tavily_search' to find top-tier sources and 'tavily_extract' to verify key claims. Your goal is to pass high-quality URLs to the Master for deep-diving."
        }

        crawl_agent = {
            "name": "crawl-agent",
            "description": "Expert in deep extraction. Use this to scrape full text, technical docs, and structured data from specific URLs.",
            "model": "gpt-4.1",
            "tools": tavily_tools,
            "system_prompt": "You are an Extraction Specialist. Your priority is reading the FULL content of a page using 'tavily_extract'. Don't settle for snippets; get the whole story so the Master can synthesize deeply."
        }

        subagents = [research_agent, crawl_agent]

        system_prompt = """You are the Master Deep Agent, an elite research orchestrator. Your goal is to move beyond simple search engine results and perform true deep research.
        
        ### Operational Protocol:
        
        #### Phase 1: Planning
        Generate a comprehensive todo list. Include steps for both Discovery (Search) and Deep-Dive (Extraction).
        
        #### Phase 2: Information Gathering (THOROUGH)
        Research is a two-stage process of Discovery then Extraction.
        1. **Discovery (Search)**: Use tools like `tavily_search` to find high-quality URLs. **IMPORTANT**: Search snippets are only for discovery; they are NOT sufficient for comprehensive research.
        2. **Deep-Dive (Extraction)**: For the top 3-5 most relevant URLs found during discovery, you **MUST** use `tavily_extract` or `tavily_crawl` to retrieve the full page content.
        - **DO NOT** summarize until you have read the actual body text of these primary sources.
        - **DO NOT** provide a summary after every tool call. Maintain silence while the research agents work.
        - Execute tools until every research-related todo in your plan is marked as complete.
        
        #### Phase 3: Unified Synthesis & Final Report
        Only when the full content of relevant primary sources has been analyzed, provide your response.
        - Produce a **Unified Final Report** that is professional, deeply synthesized, and multi-layered.
        - Connect insights across different extracted sources.
        - End with a dedicated "Sources & References" section.
        
        ### Visualization Note:
        The UI visualizes your progress automatically. Focus your output on elite synthesis. If you are still in Phase 2, proceed through the plan without stopping to chat until the deep extraction is complete.
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
