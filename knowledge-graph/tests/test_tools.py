"""
Integration tests for the agent tools layer.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from dotenv import load_dotenv

load_dotenv()


class TestSearchEntities:
    async def test_returns_results(self):
        from src.tools import search_entities
        results = await search_entities("blood thinner anticoagulant", limit=3)
        assert len(results) > 0
        assert all("id" in r and "name" in r and "node_type" in r for r in results)

    async def test_filters_by_type(self):
        from src.tools import search_entities
        results = await search_entities("diabetes", node_type="drug", limit=3)
        assert len(results) > 0
        assert all(r["node_type"] == "drug" for r in results)

    async def test_excludes_concepts_by_default(self):
        from src.tools import search_entities
        results = await search_entities("cardiovascular treatments", limit=5)
        assert all(r["node_type"] != "concept" for r in results)


class TestSearchConcepts:
    async def test_returns_concepts(self):
        from src.tools import search_concepts
        results = await search_concepts("pain management", limit=3)
        assert len(results) > 0
        assert all("description" in r for r in results)

    async def test_finds_cardiovascular(self):
        from src.tools import search_concepts
        results = await search_concepts("heart blood pressure cardiovascular", limit=3)
        names = [r["name"] for r in results]
        assert any("cardio" in n.lower() or "anticoag" in n.lower() for n in names), \
            f"Expected cardiovascular concept, got: {names}"


class TestFindRelated:
    async def test_finds_warfarin_interactions(self):
        from src.tools import find_related
        results = await find_related("Warfarin", relationship_type="INTERACTS_WITH")
        assert len(results) >= 3
        names = [r["name"] for r in results]
        assert "Aspirin" in names

    async def test_multi_hop(self):
        from src.tools import find_related
        results = await find_related("Warfarin", depth=2)
        assert len(results) > 5, "Two-hop should find many nodes"


class TestExpandConcept:
    async def test_expands_community(self):
        from src.tools import tool_expand_concept
        result = await tool_expand_concept("Diabetes Management")
        assert "members" in result
        assert len(result["members"]) >= 3
        assert "description" in result


class TestFindSharedConnections:
    async def test_finds_shared(self):
        from src.tools import tool_find_shared_connections
        result = await tool_find_shared_connections("Warfarin", "Aspirin")
        total = len(result["shared_neighbors"]) + len(result["shared_communities"])
        assert total >= 1, "Warfarin and Aspirin should share connections"


class TestFindSimilarByGraph:
    async def test_finds_similar(self):
        from src.tools import tool_find_similar_by_graph
        results = await tool_find_similar_by_graph("Warfarin", strategy="shared_neighbors", limit=3)
        assert len(results) > 0
        assert all("shared_count" in r for r in results)
