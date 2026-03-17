"""
Interactive CLI demo agent for the biomedical knowledge graph.

The agent is **truly agentic**: the LLM sees tool descriptions, decides
which tools to call, we execute them and return results, the LLM reasons
and either calls more tools or gives a final answer.  No hardcoded pipeline.

Usage:
    cd knowledge-graph
    uv run python agent.py

Type questions and see the agent use search + graph tools to answer.
Type 'quit' to exit.
"""

import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()

# Suppress noisy library loggers — only errors
for _name in ("azure", "httpx", "asyncpg", "httpcore", "urllib3", "msal"):
    logging.getLogger(_name).setLevel(logging.ERROR)
logging.basicConfig(level=logging.WARNING)

from src.tools import (
    search_entities,
    search_concepts,
    find_related,
    tool_expand_concept,
    tool_find_shared_connections,
    tool_find_similar_by_graph,
    _get_client,
)
from src.db import close_pool

# ── Tool definitions for OpenAI function-calling ─────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": "Hybrid semantic+keyword search on entity nodes (drugs, diseases, genes, symptoms, pathways). Use as the starting point for depth-first graph exploration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language search query"},
                    "node_type": {"type": "string", "enum": ["drug", "disease", "gene", "symptom", "pathway"], "description": "Optional filter by entity type"},
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_concepts",
            "description": "Hybrid search on concept/community nodes (therapeutic areas like 'Cardiovascular Treatments', 'Diabetes Management'). Use as the starting point for breadth-first exploration of an entire therapeutic landscape.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language search query"},
                    "limit": {"type": "integer", "description": "Max results (default 3)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_related",
            "description": "Graph traversal: follow edges from a named node to discover connected entities. Supports filtering by relationship type and multi-hop depth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {"type": "string", "description": "Exact name of the starting node"},
                    "relationship_type": {
                        "type": "string",
                        "enum": ["TREATS", "CAUSES_SIDE_EFFECT", "TARGETS_GENE", "INTERACTS_WITH", "ASSOCIATED_WITH", "PRESENTS_AS", "INVOLVES_PATHWAY", "PART_OF_PATHWAY", "CONTRAINDICATED", "BELONGS_TO_COMMUNITY"],
                        "description": "Optional: only follow this edge type",
                    },
                    "depth": {"type": "integer", "description": "Hop count: 1=direct neighbors (default), 2=two hops for indirect connections"},
                },
                "required": ["node_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expand_concept",
            "description": "BFS expansion: get all member entities and internal relationships of a concept/community node. Returns the community description, member list, and connections between members.",
            "parameters": {
                "type": "object",
                "properties": {
                    "concept_name": {"type": "string", "description": "Exact name of the concept node"},
                },
                "required": ["concept_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_shared_connections",
            "description": "Find what two entities have in common: shared neighbors (entities connected to both) and shared community memberships. Reveals non-obvious relationships.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name_1": {"type": "string", "description": "First entity name"},
                    "node_name_2": {"type": "string", "description": "Second entity name"},
                },
                "required": ["node_name_1", "node_name_2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_by_graph",
            "description": "Find entities that are structurally most similar to a given node in the graph — by shared neighbors or shared community memberships.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {"type": "string", "description": "Entity name to compare against"},
                    "strategy": {"type": "string", "enum": ["shared_neighbors", "shared_communities"], "description": "Similarity strategy (default: shared_neighbors)"},
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                },
                "required": ["node_name"],
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are a biomedical knowledge assistant with access to a knowledge graph containing
drugs, diseases, genes, symptoms, biological pathways, and higher-level therapeutic concepts.

You have tools to search the knowledge graph.
Use the available tools when helpful, then answer clearly and concisely.
"""

# ── Tool dispatch ────────────────────────────────────────────────────

TOOL_DISPATCH = {
    "search_entities": search_entities,
    "search_concepts": search_concepts,
    "find_related": find_related,
    "expand_concept": tool_expand_concept,
    "find_shared_connections": tool_find_shared_connections,
    "find_similar_by_graph": tool_find_similar_by_graph,
}


def _fmt_args(args: dict) -> str:
    """Compact formatting of tool arguments for display."""
    parts = []
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 40:
            v = v[:37] + "..."
        parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def _fmt_result_summary(name: str, result) -> str:
    """One-line summary of a tool result for display."""
    if isinstance(result, list):
        if not result:
            return "→ (empty)"
        names = [r.get("name", "?") for r in result[:5] if isinstance(r, dict)]
        suffix = f" +{len(result)-5} more" if len(result) > 5 else ""
        return f"→ {len(result)} results: {', '.join(names)}{suffix}"
    if isinstance(result, dict):
        if "error" in result:
            return f"→ error: {result['error']}"
        if "members" in result:
            members = [m.get("name", "?") for m in result["members"][:4]]
            return f"→ {len(result['members'])} members: {', '.join(members)}..."
        if "shared_neighbors" in result:
            n = len(result["shared_neighbors"])
            c = len(result.get("shared_communities", []))
            return f"→ {n} shared neighbors, {c} shared communities"
        return f"→ {json.dumps(result, default=str)[:80]}..."
    return f"→ {str(result)[:80]}"


async def run_agent(question: str, *, show_trace: bool = True) -> tuple[str, list[dict]]:
    """
    Run the agentic tool-calling loop. Returns (answer, tool_trace).

    The LLM decides which tools to call at each step.
    """
    client = _get_client()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    tool_trace: list[dict] = []

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for iteration in range(8):  # safety cap
        resp = client.chat.completions.create(
            model=deployment,
            messages=messages,
            tools=TOOLS_SCHEMA,
            temperature=0.3,
        )
        choice = resp.choices[0]

        # If the LLM wants to call tools
        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            messages.append(choice.message)

            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)

                # Execute
                fn = TOOL_DISPATCH.get(fn_name)
                if fn is None:
                    result = {"error": f"Unknown tool: {fn_name}"}
                else:
                    try:
                        result = await fn(**fn_args)
                    except Exception as e:
                        result = {"error": str(e)}

                # Record trace
                trace_entry = {"tool": fn_name, "args": fn_args, "summary": _fmt_result_summary(fn_name, result)}
                tool_trace.append(trace_entry)

                if show_trace:
                    print(f"  🔧 {fn_name}({_fmt_args(fn_args)})")
                    print(f"     {trace_entry['summary']}")

                # Feed result back to LLM
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })
        else:
            # LLM is done — return the final answer
            return choice.message.content or "(no answer)", tool_trace

    return "(agent hit iteration limit)", tool_trace


EXAMPLE_QUESTIONS = [
    "What is Warfarin used for?",
    "What is Metformin used for?",
    "What symptoms are associated with Hypertension?",
    "What is CYP2D6?",
    "Explain the Coagulation Cascade.",
]


async def main():
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  Biomedical Knowledge Graph Agent  (truly agentic)         ║")
    print("║  The LLM decides which tools to call and when.             ║")
    print("║  Type a question, or 'examples' for sample questions.      ║")
    print("║  Type 'quit' to exit.                                      ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    while True:
        try:
            question = input("❓ You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            break
        if question.lower() == "examples":
            print("\nExample questions:")
            for i, q in enumerate(EXAMPLE_QUESTIONS, 1):
                print(f"  {i}. {q}")
            print()
            continue

        if question.isdigit() and 1 <= int(question) <= len(EXAMPLE_QUESTIONS):
            question = EXAMPLE_QUESTIONS[int(question) - 1]
            print(f"  → {question}")

        print("\n  ── Agent reasoning ──")
        try:
            answer, trace = await run_agent(question)
            print(f"\n  ── Tool calls: {len(trace)} ──\n")
            print(f"🤖 Agent:\n{answer}\n")
        except Exception as e:
            print(f"❌ Error: {e}\n")

    await close_pool()
    print("Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
