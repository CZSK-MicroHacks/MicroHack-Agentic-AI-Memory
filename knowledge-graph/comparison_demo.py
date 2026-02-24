"""
Comparison demo: RAG-only (hybrid search) vs Agentic Graph search.

RAG-only: embed the question → hybrid search → feed top results to LLM.
Agentic:  LLM decides which tools to call (search, traverse, expand, etc.).

Shows side-by-side tool traces and answers for questions where graph wins.
"""

import asyncio
import json
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()

# Suppress all library noise — only errors
for _name in ("azure", "httpx", "asyncpg", "httpcore", "urllib3", "msal"):
    logging.getLogger(_name).setLevel(logging.ERROR)
logging.basicConfig(level=logging.WARNING)


QUESTIONS = [
    {
        "question": "A patient on Warfarin has a headache. What pain medications should they avoid?",
        "expected": "Should list Aspirin, Ibuprofen, Clopidogrel as specific drugs that interact with Warfarin.",
    },
    {
        "question": "What do Metformin and Lisinopril have in common?",
        "expected": "Should find shared neighbors (e.g. Gabapentin) and shared community/pathway memberships.",
    },
    {
        "question": "What is the landscape of cardiovascular treatments?",
        "expected": "Should expand cardiovascular concept to list all member drugs, diseases, and pathways.",
    },
    {
        "question": "Could diabetes medication affect bleeding risk?",
        "expected": "Should trace multi-hop path: diabetes drugs → side effects/interactions → bleeding-related drugs.",
    },
    {
        "question": "Which drugs are most likely to have dangerous interactions?",
        "expected": "Should rank drugs by INTERACTS_WITH edge count, identifying Warfarin and Aspirin as top.",
    },
]


async def rag_only(question: str) -> tuple[str, list[str]]:
    """RAG-only: hybrid search → top results → LLM answer."""
    from src.tools import _embed, _get_client
    from src.search import hybrid_search

    embedding = _embed(question)
    results = await hybrid_search(question, embedding, limit=5)

    trace = [f"hybrid_search(query={question!r:.50}, limit=5) → {len(results)} results"]

    context = "\n".join(
        f"- [{r['node_type']}] {r['name']}: {r['description']}"
        for r in results
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
    return resp.choices[0].message.content, trace


async def agentic_graph(question: str) -> tuple[str, list[str]]:
    """Agentic: LLM decides tools via function calling."""
    from agent import run_agent, _fmt_args
    answer, tool_trace = await run_agent(question, show_trace=False)
    trace = [
        f"{t['tool']}({_fmt_args(t['args'])}) {t['summary']}"
        for t in tool_trace
    ]
    return answer, trace


def _wrap(text: str, width: int = 76, indent: str = "     ") -> str:
    """Wrap long text for clean CLI output."""
    import textwrap
    return "\n".join(
        textwrap.fill(line, width=width, initial_indent=indent, subsequent_indent=indent)
        if line.strip() else ""
        for line in text.split("\n")
    )


async def main():
    from src.db import close_pool

    print()
    print("═" * 80)
    print("  COMPARISON: RAG-only vs Agentic Graph Search")
    print("  Biomedical Drug Interactions Knowledge Graph")
    print("═" * 80)

    for i, q in enumerate(QUESTIONS, 1):
        print()
        print("─" * 80)
        print(f"  Q{i}: {q['question']}")
        print(f"  🎯 Expected: {q['expected']}")
        print("─" * 80)

        # ── RAG-only ──
        rag_answer, rag_trace = await rag_only(q["question"])
        print()
        print("  📄 RAG-only (hybrid search → LLM)")
        print("  Tool calls:")
        for t in rag_trace:
            print(f"     • {t}")
        print("  Answer:")
        print(_wrap(rag_answer))

        # ── Agentic Graph ──
        graph_answer, graph_trace = await agentic_graph(q["question"])
        print()
        print("  🔗 Agentic Graph (LLM decides tools)")
        print(f"  Tool calls ({len(graph_trace)}):")
        for t in graph_trace:
            print(f"     • {t}")
        print("  Answer:")
        print(_wrap(graph_answer))

    print()
    print("═" * 80)
    print("  ✅ Comparison complete!")
    print("     RAG-only returns document snippets; the agent uses graph traversal to")
    print("     discover relationships, shared connections, and multi-hop paths that")
    print("     plain search cannot surface.")
    print("═" * 80)
    print()

    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
