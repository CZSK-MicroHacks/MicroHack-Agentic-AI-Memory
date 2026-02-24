"""
Interactive CLI demo agent for the biomedical knowledge graph.

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

SYSTEM_PROMPT = """\
You are a biomedical knowledge assistant with access to a knowledge graph containing
drugs, diseases, genes, symptoms, biological pathways, and higher-level therapeutic concepts.

You have these tools available (already executed — the results are provided below):
- search_entities: hybrid semantic+keyword search on entity nodes
- search_concepts: hybrid search on community/concept nodes
- find_related: graph traversal to find connected nodes (DFS)
- expand_concept: BFS expansion of a concept community
- find_shared_connections: find common neighbors between two nodes
- find_similar_by_graph: find structurally similar nodes

Use the tool results to give a comprehensive, accurate answer.
Always cite which relationships or connections support your answer.
"""


async def answer_question(question: str) -> str:
    """Use tools to gather context, then generate an LLM answer."""
    # Step 1: Search for relevant entities and concepts
    entities = await search_entities(question, limit=3)
    concepts = await search_concepts(question, limit=2)

    # Step 2: Graph traversal from top entity results
    graph_context = []
    for entity in entities[:2]:
        neighbors = await find_related(entity["name"])
        graph_context.append({
            "node": entity["name"],
            "type": entity["node_type"],
            "connections": [
                {"name": n["name"], "via": n["relationship_type"]}
                for n in neighbors[:10]
            ],
        })

    # Step 3: Expand top concept
    concept_detail = None
    if concepts:
        concept_detail = await tool_expand_concept(concepts[0]["name"])

    # Step 4: If 2+ entities, find shared connections
    shared = None
    if len(entities) >= 2:
        shared = await tool_find_shared_connections(entities[0]["name"], entities[1]["name"])

    # Build context for LLM
    context_parts = []
    context_parts.append("## Entity Search Results")
    for e in entities:
        context_parts.append(f"- [{e['node_type']}] {e['name']}: {e['description']}")

    context_parts.append("\n## Concept Search Results")
    for c in concepts:
        context_parts.append(f"- {c['name']}: {c['description'][:200]}")

    context_parts.append("\n## Graph Traversal (connections)")
    for g in graph_context:
        context_parts.append(f"\n### {g['node']} ({g['type']})")
        for conn in g["connections"]:
            context_parts.append(f"  → {conn['name']} (via {conn['via']})")

    if concept_detail and "members" in concept_detail:
        context_parts.append(f"\n## Concept Expansion: {concept_detail['concept']}")
        context_parts.append(f"Description: {concept_detail.get('description', '')[:300]}")
        members = [m["name"] for m in concept_detail.get("members", [])]
        context_parts.append(f"Members: {', '.join(members)}")
        for rel in concept_detail.get("internal_relationships", [])[:5]:
            context_parts.append(f"  {rel['source']} --[{rel['relationship']}]--> {rel['target']}")

    if shared:
        context_parts.append(f"\n## Shared Connections: {shared['node_1']} ↔ {shared['node_2']}")
        for s in shared.get("shared_neighbors", [])[:5]:
            context_parts.append(
                f"  Common: {s['shared_node']} "
                f"({s['relationship_to_first']} / {s['relationship_to_second']})"
            )
        if shared.get("shared_communities"):
            context_parts.append(f"  Shared communities: {', '.join(shared['shared_communities'])}")

    context = "\n".join(context_parts)

    # Step 5: LLM generates final answer
    client = _get_client()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context from knowledge graph:\n\n{context}\n\nQuestion: {question}"},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content


EXAMPLE_QUESTIONS = [
    "A patient on Warfarin has a headache. What pain medications should they avoid?",
    "What do Metformin and Lisinopril have in common?",
    "Describe the landscape of cardiovascular treatments.",
    "Could diabetes medication affect bleeding risk?",
    "What are the most important drug interactions to watch for?",
]


async def main():
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  Biomedical Knowledge Graph Agent                          ║")
    print("║  Type a question, or 'examples' to see sample questions.   ║")
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

        # Check if user typed a number for example questions
        if question.isdigit() and 1 <= int(question) <= len(EXAMPLE_QUESTIONS):
            question = EXAMPLE_QUESTIONS[int(question) - 1]
            print(f"  → {question}")

        print("\n🔍 Searching knowledge graph...\n")
        try:
            answer = await answer_question(question)
            print(f"🤖 Agent:\n{answer}\n")
        except Exception as e:
            print(f"❌ Error: {e}\n")

    await close_pool()
    print("Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
