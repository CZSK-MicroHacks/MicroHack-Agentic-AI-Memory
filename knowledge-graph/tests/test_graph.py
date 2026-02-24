"""
Tests for graph traversal via AGE Cypher queries.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from dotenv import load_dotenv

load_dotenv()


class TestGetNeighbors:
    @pytest.mark.asyncio
    async def test_warfarin_has_neighbors(self):
        from src.graph import get_neighbors
        results = await get_neighbors("Warfarin")
        assert len(results) > 0
        names = [r["name"] for r in results]
        # Warfarin should have interactions, treats, side effects
        assert any("VKORC1" in n or "Aspirin" in n or "Deep Vein" in n for n in names), \
            f"Expected known Warfarin connections, got: {names}"

    @pytest.mark.asyncio
    async def test_filter_by_relationship_type(self):
        from src.graph import get_neighbors
        results = await get_neighbors("Warfarin", relationship_type="INTERACTS_WITH")
        assert len(results) > 0
        # All should be drug interactions
        assert all(r["relationship_type"] == "INTERACTS_WITH" for r in results)

    @pytest.mark.asyncio
    async def test_two_hop_traversal(self):
        from src.graph import get_neighbors
        results = await get_neighbors("Warfarin", depth=2)
        # 2-hop should find more nodes than 1-hop
        one_hop = await get_neighbors("Warfarin", depth=1)
        assert len(results) >= len(one_hop), "Two-hop should find at least as many nodes"


class TestSharedConnections:
    @pytest.mark.asyncio
    async def test_find_commonality(self):
        from src.graph import find_shared_connections
        result = await find_shared_connections("Warfarin", "Aspirin")
        assert "shared_neighbors" in result
        assert "shared_communities" in result
        # Both are drugs that interact — they should share some connections
        total = len(result["shared_neighbors"]) + len(result["shared_communities"])
        assert total > 0, "Warfarin and Aspirin should share some connections"


class TestExpandCommunity:
    @pytest.mark.asyncio
    async def test_expand_existing_concept(self):
        from src.graph import expand_community
        result = await expand_community("Anticoagulation Therapy")
        assert "members" in result
        assert len(result["members"]) > 0
        member_names = [m["name"] for m in result["members"]]
        assert "Warfarin" in member_names, f"Expected Warfarin in Anticoagulation Therapy, got: {member_names}"

    @pytest.mark.asyncio
    async def test_expand_nonexistent_concept(self):
        from src.graph import expand_community
        result = await expand_community("Nonexistent Concept XYZ")
        assert "error" in result


class TestFindSimilar:
    @pytest.mark.asyncio
    async def test_similar_by_shared_neighbors(self):
        from src.graph import find_similar_by_graph
        results = await find_similar_by_graph("Warfarin", strategy="shared_neighbors", limit=5)
        assert len(results) > 0
        # Results should have shared_count > 0
        assert all(r["shared_count"] > 0 for r in results)

    @pytest.mark.asyncio
    async def test_similar_by_shared_communities(self):
        from src.graph import find_similar_by_graph
        results = await find_similar_by_graph("Warfarin", strategy="shared_communities", limit=5)
        assert len(results) > 0
