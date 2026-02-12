# frontend — A2UI Native Rendering Frontend

A lightweight Lit (Web Components) app that **natively renders A2UI protocol components** from tool-call results. It also provides a full chat UI with sessions, conversation history, memory search, and user profile memory.

## UI features

- Live chat with streaming responses and tool-call surfaces
- Session list with create/rename/delete
- Conversation history with resume + rename
- Memory list + semantic search with detail view
- User profile drawer with generate/update/delete

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Backend (server.py)                            │
│  Sends AG-UI SSE events:                        │
│    TEXT_MESSAGE_CONTENT, TOOL_CALL_RESULT, ...  │
│  Tool results are plain JSON                    │
└────────────────────┬────────────────────────────┘
                     │ SSE
┌────────────────────▼────────────────────────────┐
│  Frontend (frontend)                            │
│                                                  │
│  1. client.ts        → REST + SSE (chat + data) │
│  2. converters.ts    → tool JSON → A2UI messages│
│  3. a2ui/processor   → buffers & builds surfaces│
│  4. a2ui/surface     → renders A2UI components  │
│                        (Card, Column, Row, Text,│
│                         Icon, Button, Image…)   │
└─────────────────────────────────────────────────┘
```

### Key files

| File | Purpose |
|---|---|
| `src/a2ui/types.ts` | A2UI v0.8 message type definitions |
| `src/a2ui/processor.ts` | A2UI message processor (buffers components + data model) |
| `src/a2ui/surface-renderer.ts` | `<a2ui-surface>` — recursive native component renderer |
| `src/converters.ts` | Tool-result → A2UI message converters + template inflater |
| `src/templates/` | Declarative A2UI surface templates |
| `src/client.ts` | REST + SSE client (chat, sessions, history, memory, profile) |
| `src/app.ts` | Main app shell (chat, sidebar, memory, profile) |

## Running

```bash
cd frontend
npm install
npm run dev
```

Opens at **http://localhost:5175** (proxies `/api` → `http://localhost:8000`).

Make sure the backend is running:
```bash
cd ..
uv run server.py
```

If you deploy behind a different API base URL, set `window.__APP_CONFIG__.apiBaseUrl` at runtime.

## Adding new converters

To render a new tool's results natively, add a template and a converter in `src/converters.ts`:

```ts
converters.set('my_tool_name', (result, surfaceId) => {
  // Use a template + data model, return [surfaceUpdate, dataModelUpdate, beginRendering]
});
```

No custom Lit components needed — the A2UI renderer handles it all.
