"""
FastAPI backend for the graphical comparison demo.

Exposes an SSE streaming endpoint that progressively sends tool calls and
answers for both RAG-only and agentic graph approaches.
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()

# Suppress library noise
for _name in ("azure", "httpx", "asyncpg", "httpcore", "urllib3", "msal"):
    logging.getLogger(_name).setLevel(logging.ERROR)
logging.basicConfig(level=logging.WARNING)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Knowledge Graph Comparison Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Questions ──

QUESTIONS = [
    {"id": 1, "question": "What is Warfarin used for?"},
    {"id": 2, "question": "What is Metformin used for?"},
    {"id": 3, "question": "What symptoms are associated with Hypertension?"},
    {"id": 4, "question": "What is CYP2D6?"},
    {"id": 5, "question": "Explain the Coagulation Cascade."},
]


@app.get("/api/questions")
async def get_questions():
    return QUESTIONS


def _sse(event: str, data: dict) -> str:
    """Format a server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_comparison(question: str):
    """Generator that yields SSE events as each step completes."""
    from src.tools import _embed, _get_client
    from src.search import hybrid_search
    from agent import (
        TOOLS_SCHEMA, SYSTEM_PROMPT, TOOL_DISPATCH,
        _fmt_args, _fmt_result_summary,
    )

    # ── Phase 1: RAG-only ──
    yield _sse("rag_start", {})

    embedding = _embed(question)
    results = await hybrid_search(question, embedding, limit=5)
    tool_str = f"hybrid_search(query={question!r:.50}, limit=5) -> {len(results)} results"
    yield _sse("rag_tool", {"tool": tool_str})

    context = "\n".join(
        f"- [{r['node_type']}] {r['name']}: {r['description']}" for r in results
    )
    client = _get_client()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "You are a biomedical assistant. Answer based ONLY on the provided search results. If the results don't contain enough info, say so."},
            {"role": "user", "content": f"Search results:\n{context}\n\nQuestion: {question}"},
        ],
        temperature=0.3,
    )
    yield _sse("rag_answer", {"answer": resp.choices[0].message.content})

    # ── Phase 2: Agentic graph (streaming tool calls) ──
    yield _sse("graph_start", {})

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for _ in range(8):
        resp = client.chat.completions.create(
            model=deployment,
            messages=messages,
            tools=TOOLS_SCHEMA,
            temperature=0.3,
        )
        choice = resp.choices[0]

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            messages.append(choice.message)
            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)

                fn = TOOL_DISPATCH.get(fn_name)
                if fn is None:
                    result = {"error": f"Unknown tool: {fn_name}"}
                else:
                    try:
                        result = await fn(**fn_args)
                    except Exception as e:
                        result = {"error": str(e)}

                summary = _fmt_result_summary(fn_name, result)
                yield _sse("graph_tool", {
                    "tool": f"{fn_name}({_fmt_args(fn_args)})",
                    "summary": summary,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })
        else:
            yield _sse("graph_answer", {"answer": choice.message.content or "(no answer)"})
            break

    yield _sse("done", {})


@app.get("/api/compare/{question_id}")
async def compare_stream(question_id: int):
    q = next((q for q in QUESTIONS if q["id"] == question_id), None)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    return StreamingResponse(
        _stream_comparison(q["question"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Mount frontend static files (built React app)
_frontend_dist = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8080, reload=True)
