"""
FastAPI backend for the graphical comparison demo.

Exposes endpoints to run RAG-only and agentic graph search for the 5 curated
questions, with tool call traces and streaming support.
"""

import asyncio
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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Knowledge Graph Comparison Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Questions ──

QUESTIONS = [
    {
        "id": 1,
        "question": "A patient on Warfarin has a headache. What pain medications should they avoid?",
        "expected": "Should list Aspirin, Ibuprofen, Clopidogrel as specific drugs that interact with Warfarin.",
    },
    {
        "id": 2,
        "question": "What do Metformin and Lisinopril have in common?",
        "expected": "Should find shared neighbors (e.g. Gabapentin) and shared community/pathway memberships.",
    },
    {
        "id": 3,
        "question": "What is the landscape of cardiovascular treatments?",
        "expected": "Should expand cardiovascular concept to list all member drugs, diseases, and pathways.",
    },
    {
        "id": 4,
        "question": "Could diabetes medication affect bleeding risk?",
        "expected": "Should trace multi-hop path: diabetes drugs → side effects/interactions → bleeding-related drugs.",
    },
    {
        "id": 5,
        "question": "Which drugs are most likely to have dangerous interactions?",
        "expected": "Should rank drugs by INTERACTS_WITH edge count, identifying Warfarin and Aspirin as top.",
    },
]


class CompareResult(BaseModel):
    question: str
    expected: str
    rag_answer: str
    rag_tools: list[str]
    graph_answer: str
    graph_tools: list[str]


@app.get("/api/questions")
async def get_questions():
    return QUESTIONS


@app.post("/api/compare/{question_id}")
async def compare(question_id: int) -> CompareResult:
    q = next((q for q in QUESTIONS if q["id"] == question_id), None)
    if not q:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Question not found")

    from comparison_demo import rag_only, agentic_graph

    rag_answer, rag_tools = await rag_only(q["question"])
    graph_answer, graph_tools = await agentic_graph(q["question"])

    return CompareResult(
        question=q["question"],
        expected=q["expected"],
        rag_answer=rag_answer,
        rag_tools=rag_tools,
        graph_answer=graph_answer,
        graph_tools=graph_tools,
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
