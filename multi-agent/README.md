# Challenge 06: Multi-Agent Travel Planner — Agents Scratchpad

A multi-agent travel planning demo showcasing **shared scratchpad memory** for agent coordination. Specialist agents collaborate to plan trips by reading and writing to shared memory tools instead of passing large context in messages.

## Architecture

```
                     ┌──────────────────────────────────────┐
                     │           User (React UI)            │
                     └──────────────┬───────────────────────┘
                                    │ POST /chat (SSE stream)
                     ┌──────────────▼───────────────────────┐
                     │        FastAPI Server                 │
                     │     (server.py + orchestrator.py)     │
                     └──────────────┬───────────────────────┘
                                    │
                     ┌──────────────▼───────────────────────┐
                     │      Facilitator Agent                │
                     │  Creates plan, dispatches specialists │
                     └──┬────────┬────────┬────────┬────────┘
                        │        │        │        │
                   ┌────▼──┐ ┌──▼────┐ ┌─▼─────┐ ┌▼──────┐
                   │Logis- │ │Sights-│ │Experi-│ │Food & │
                   │tics   │ │seeing │ │ence   │ │Drink  │
                   └───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘
                       │         │         │         │
                ┌──────▼─────────▼─────────▼─────────▼──────┐
                │           Shared Scratchpads               │
                │  ┌─────────────┐  ┌─────────────────────┐ │
                │  │ Task        │  │ Shared Document     │ │
                │  │ Board       │  │ (with versioning)   │ │
                │  └─────────────┘  └─────────────────────┘ │
                └───────────────────────────────────────────┘
```

## Key Concepts

### Scratchpad Memory Pattern
Instead of passing large context between agents in messages, agents communicate through **shared memory tools**:

- **Task Board** — The Facilitator creates numbered tasks assigned to specialists. Agents read their tasks, do the work, and mark them complete. The Facilitator monitors progress.
- **Shared Document** — All agents contribute to a collaborative travel plan. Each write creates a new version, enabling full history tracking.

### Why Scratchpads?
- **Smaller messages** — Agents reference task IDs instead of repeating full descriptions
- **Shared state** — All agents can see what others have written
- **Audit trail** — Version history shows how the document evolved
- **Coordination** — Task board tracks what's done and what's pending

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Azure OpenAI resource (or API key)

### Backend

```bash
cd multi-agent/backend

# Copy and configure environment
cp .env.example .env
# Edit .env with your Azure OpenAI endpoint and deployment

# Install dependencies (using uv)
uv sync

# Run the server
uv run uvicorn server:app --port 8000
```

### Frontend

```bash
cd multi-agent/frontend

# Install dependencies
npm install

# Run dev server (proxies to backend on port 8000)
npm run dev
```

Open http://localhost:5173 in your browser.

## How It Works

### Workflow Flow
1. **User asks**: "Plan a 3-day trip to Prague for a couple who loves history and craft beer"
2. **Facilitator** analyzes the request and creates task board with specific tasks
3. **Facilitator** dispatches specialists one by one, referencing task IDs
4. Each **specialist**:
   - Reads assigned tasks from the scratchpad
   - Generates recommendations (using LLM knowledge)
   - Writes findings to the shared document
   - Marks tasks as complete
5. **Facilitator** checks all tasks are done, reads the full document, composes final answer

### UI Dashboard (3 panels)
- **Left: Chat** — Send your travel request, see the final plan
- **Center: Agent Timeline** — Watch agents work in real-time (starts, tool calls, messages)
- **Right: Scratchpads** — Task board (top) and shared document with version history (bottom)

## File Structure

```
multi-agent/
├── backend/
│   ├── server.py          # FastAPI app, SSE streaming
│   ├── orchestrator.py    # Facilitator agent + workflow orchestration
│   ├── agents.py          # Specialist agent definitions
│   ├── scratchpad.py      # TaskBoard + SharedDocument classes
│   ├── tools.py           # @tool functions for scratchpad access
│   ├── events.py          # SSE event emitter
│   ├── prompts/           # Jinja2 agent prompt templates
│   ├── pyproject.toml     # Python dependencies
│   └── .env.example       # Environment config template
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # Main 3-panel layout
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx          # Chat input + final answer
│   │   │   ├── TaskBoard.tsx          # Live task list with progress bar
│   │   │   ├── DocumentViewer.tsx     # Document + version selector
│   │   │   ├── AgentTimeline.tsx      # Activity feed with tool calls
│   │   │   └── Header.tsx             # App header
│   │   ├── hooks/
│   │   │   └── useEventStream.ts      # SSE connection hook
│   │   ├── types.ts                   # Shared TypeScript types
│   │   └── index.css                  # Tailwind + custom styles
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Technologies

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Agent Framework | Microsoft Agent Framework (`agent-framework-ag-ui`) | ChatAgent, tools, streaming |
| LLM | Azure OpenAI (gpt-4o-mini) | Agent reasoning |
| Backend | Python FastAPI | API server, SSE streaming |
| Frontend | React + Vite + TypeScript | Dashboard UI |
| Styling | Tailwind CSS | Responsive layout |
| Scratchpads | In-memory Python objects | Shared state (no external DB needed) |
