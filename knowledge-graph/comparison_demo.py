"""
Comparison demo: RAG-only (hybrid search) vs Graph-enhanced search.

Shows side-by-side results for questions where graph traversal provides
significantly better answers than plain semantic/keyword search alone.
"""

import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kg.comparison")


# Test questions designed to show graph advantage
QUESTIONS = [
    {
        "question": "A patient on Warfarin has a headache. What pain medications should they avoid?",
        "why_graph_wins": "Requires: find Warfarin → interacts_with → drugs, then check which treat pain",
        "expected_graph_finds": ["Aspirin", "Ibuprofen"],
    },
    {
        "question": "What do Metformin and Lisinopril have in common?",
        "why_graph_wins": "Requires: shared neighbors, shared pathways, shared communities",
        "expected_graph_finds": ["shared connections", "communities"],
    },
    {
        "question": "What is the landscape of cardiovascular treatments?",
        "why_graph_wins": "Requires: concept-level summary + BFS to all connected entities",
        "expected_graph_finds": ["Cardiovascular", "members", "relationships"],
    },
    {
        "question": "Could diabetes medication affect bleeding risk?",
        "why_graph_wins": "Requires multi-hop: Metformin → diabetes → genes → coagulation → Warfarin",
        "expected_graph_finds": ["indirect path", "multi-hop"],
    },
    {
        "question": "Which drugs are most likely to have dangerous interactions?",
        "why_graph_wins": "Requires: graph analysis of INTERACTS_WITH edge density",
        "expected_graph_finds": ["most connected", "interaction count"],
    },
]


async def rag_only_answer(question: str) -> dict:
    """Answer using only hybrid search (no graph traversal)."""
    from src.tools import _embed
    from src.search import hybrid_search

    embedding = _embed(question)
    results = await hybrid_search(question, embedding, limit=5)

    return {
        "method": "RAG-only (hybrid search)",
        "results": [
            {"name": r["name"], "type": r["node_type"], "description": r["description"][:100]}
            for r in results
        ],
    }


async def graph_enhanced_answer(question: str) -> dict:
    """Answer using hybrid search + graph traversal."""
    from src.tools import _embed, search_entities, search_concepts, find_related
    from src.graph import find_shared_connections, expand_community, find_similar_by_graph

    # Step 1: Hybrid search for starting nodes
    results = await search_entities(question, limit=3)
    starting_nodes = [r["name"] for r in results]

    # Step 2: Concept search for community context
    concepts = await search_concepts(question, limit=2)

    # Step 3: Graph traversal from each starting node
    graph_findings = []
    for node_name in starting_nodes:
        neighbors = await find_related(node_name)
        graph_findings.append({
            "starting_node": node_name,
            "direct_connections": [
                {"name": n["name"], "via": n["relationship_type"]}
                for n in neighbors[:8]
            ],
        })

    # Step 4: If we have 2+ starting nodes, find shared connections
    shared = None
    if len(starting_nodes) >= 2:
        shared = await find_shared_connections(starting_nodes[0], starting_nodes[1])

    # Step 5: Expand relevant concepts
    concept_details = []
    for c in concepts[:1]:
        detail = await expand_community(c["name"])
        concept_details.append({
            "concept": c["name"],
            "description": detail.get("description", "")[:150],
            "member_count": len(detail.get("members", [])),
            "internal_relationships": len(detail.get("internal_relationships", [])),
        })

    # Step 6: Graph similarity
    similar = []
    if starting_nodes:
        similar = await find_similar_by_graph(starting_nodes[0], strategy="shared_neighbors", limit=3)

    return {
        "method": "Graph-enhanced search",
        "starting_nodes": results,
        "graph_traversal": graph_findings,
        "shared_connections": shared,
        "concept_expansion": concept_details,
        "graph_similar": similar,
    }


def print_separator():
    print("=" * 80)


def print_rag_result(result: dict):
    print(f"\n  📄 {result['method']}:")
    for r in result["results"]:
        print(f"     [{r['type']}] {r['name']}: {r['description']}...")


def print_graph_result(result: dict):
    print(f"\n  🔗 {result['method']}:")

    print("     Starting nodes (from hybrid search):")
    for r in result["starting_nodes"]:
        print(f"       [{r['node_type']}] {r['name']}")

    print("     Graph traversal findings:")
    for finding in result["graph_traversal"]:
        print(f"       From {finding['starting_node']}:")
        for conn in finding["direct_connections"][:5]:
            print(f"         → {conn['name']} (via {conn['via']})")

    if result["shared_connections"]:
        sc = result["shared_connections"]
        print(f"     Shared connections between {sc['node_1']} and {sc['node_2']}:")
        for s in sc["shared_neighbors"][:3]:
            print(f"       Common: {s['shared_node']} ({s['relationship_to_first']} / {s['relationship_to_second']})")
        if sc["shared_communities"]:
            print(f"       Shared communities: {', '.join(sc['shared_communities'])}")

    if result["concept_expansion"]:
        for c in result["concept_expansion"]:
            print(f"     Concept: {c['concept']} ({c['member_count']} members, {c['internal_relationships']} internal rels)")

    if result["graph_similar"]:
        print(f"     Most graph-similar to {result['starting_nodes'][0]['name'] if result['starting_nodes'] else '?'}:")
        for s in result["graph_similar"]:
            print(f"       {s['name']} (shared: {s['shared_count']})")


async def main():
    from src.db import close_pool

    print("\n" + "=" * 80)
    print("  COMPARISON: RAG-only vs Graph-enhanced Search")
    print("  Biomedical Drug Interactions Knowledge Graph")
    print("=" * 80)

    for i, q in enumerate(QUESTIONS, 1):
        print_separator()
        print(f"\n  Question {i}: {q['question']}")
        print(f"  Why graph wins: {q['why_graph_wins']}")

        # RAG-only
        rag_result = await rag_only_answer(q["question"])
        print_rag_result(rag_result)

        # Graph-enhanced
        graph_result = await graph_enhanced_answer(q["question"])
        print_graph_result(graph_result)

        print()

    print_separator()
    print("\n  ✅ Comparison complete!")
    print("     Graph-enhanced search reveals connections, communities,")
    print("     and multi-hop relationships that pure RAG misses.\n")

    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
