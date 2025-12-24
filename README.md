# DeepAgent 🚀

DeepAgent is an elite AI research orchestrator designed to move beyond simple search engine results. It employs a multi-agent system to perform comprehensive discovery and deep-dive extraction, synthesizing high-quality, professional reports from across the web.

## ✨ Key Features

-   **Multi-Agent Orchestration**: Features a "Master" agent coordinating specialized "Research" (Discovery) and "Crawl" (Extraction) sub-agents.
-   **Deep Research Protocol**: Uses a three-phase approach: Planning, Information Gathering (Discovery + Deep-Dive Extraction), and Unified Synthesis.
-   **Advanced Model Support**: Optimized for the latest models including GPT-4, GPT-5 (Reasoning/Thinking modes), and OpenAI o1/o3 series.
-   **Thinking/Reasoning Toggle**: Dynamic control over model reasoning effort, allowing for rapid answers or deep-thought analysis.
-   **Real-time Streaming**: A rich UI experience with streaming thoughts, status updates, tool calls, and research plans.
-   **Tavily MCP Integration**: Leverages Tavily's Model Context Protocol (MCP) for high-tier web searching and full-text extraction.
-   **Modern UI/UX**: Built with Next.js 15+, Tailwind CSS 4, Radix UI, and `@assistant-ui/react`.

---

## 🏗️ Architecture

### Backend (Python/FastAPI)
-   **Framework**: FastAPI for high-performance streaming.
-   **Agent Logic**: LangChain & LangGraph for complex agentic workflows.
-   **Research Tools**: Tavily Search & Extract via MCP.
-   **Persistence**: SQLite-based checkpointer for thread history and state management.

### Frontend (Next.js)
-   **Framework**: Next.js 15+ (App Router).
-   **Styling**: Tailwind CSS 4 & Lucide React icons.
-   **Components**: Radix UI & Shadcn UI.
-   **AI Interface**: `@assistant-ui/react` for a polished chat experience.

---

## 🚀 Getting Started

### Prerequisites
-   [Python 3.12+](https://www.python.org/downloads/)
-   [Node.js 18+](https://nodejs.org/)
-   [`uv`](https://github.com/astral-sh/uv) (Highly recommended for Python dependency management)

### 1. Clone the Repository
```bash
git clone <repository-url>
cd DeepAgent
```

### 2. Environment Configuration
Create a `.env` file in the root directory (or inside `backend/`):

```env
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
```

### 3. Backend Setup
```bash
cd backend

# Using uv (recommended)
uv sync

# Run the server
uv run python -m uvicorn app.server:app --reload --port 8000 
```
The backend will be available at `http://localhost:8000`.

### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
The frontend will be available at `http://localhost:3000`.

---

## 🛠️ Usage

1.  **Enter a Query**: Ask a complex research question (e.g., "Analyze the latest trends in quantum computing for 2025").
2.  **Watch the Plan**: The agent will first generate a research plan (Todo list) visible in the UI.
3.  **Monitor Progress**: Follow the status updates as the agent researches, crawls, and synthesizes data.
4.  **Final Report**: Receive a professional, multi-layered report with full citations and references.

---

## 📂 Project Structure

```text
DeepAgent/
├── backend/
│   ├── app/
│   │   ├── agent.py       # Agent logic & MCP setup
│   │   └── server.py      # FastAPI streaming endpoints
│   ├── pyproject.toml     # Backend dependencies
│   └── checkpoints.db     # Thread persistence
├── frontend/
│   ├── src/
│   │   ├── app/           # Next.js pages & layouts
│   │   ├── components/    # UI & Chat components
│   │   └── providers/     # Theme & State providers
│   ├── package.json       # Frontend dependencies
│   └── tailwind.config.ts # Styling configuration
└── README.md
```

