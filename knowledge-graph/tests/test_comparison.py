"""
Automated comparison tests: verify graph-enhanced search beats RAG-only on curated questions.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from dotenv import load_dotenv

load_dotenv()


class TestGraphBeatsRag:
    """Tests that graph search finds information that plain RAG misses."""

    async def test_warfarin_interactions_found_via_graph(self):
        """Graph traversal should find drug interactions that RAG alone might miss."""
        from src.graph import get_neighbors
        results = await get_neighbors("Warfarin", relationship_type="INTERACTS_WITH")
        interaction_names = [r["name"] for r in results]

        # Graph should find concrete drug-drug interactions
        assert len(interaction_names) >= 3, \
            f"Graph should find 3+ Warfarin interactions, found: {interaction_names}"
        assert "Aspirin" in interaction_names or "Ibuprofen" in interaction_names, \
            f"Graph should find Aspirin/Ibuprofen as Warfarin interactions, found: {interaction_names}"

    async def test_shared_connections_reveal_hidden_links(self):
        """Shared connections between two drugs reveal common targets that RAG can't surface."""
        from src.graph import find_shared_connections
        result = await find_shared_connections("Warfarin", "Aspirin")

        total_shared = len(result["shared_neighbors"]) + len(result["shared_communities"])
        assert total_shared >= 2, \
            f"Warfarin/Aspirin should share 2+ connections, found {total_shared}"

        # They should share at least Bleeding as a side effect
        shared_names = [s["shared_node"] for s in result["shared_neighbors"]]
        assert "Bleeding" in shared_names or "Coagulation Cascade" in shared_names, \
            f"Expected Bleeding or Coagulation Cascade in shared, got: {shared_names}"

    async def test_concept_expansion_provides_complete_picture(self):
        """Concept BFS expansion gives a complete therapeutic area view that chunk-based RAG lacks."""
        from src.graph import expand_community

        result = await expand_community("Anticoagulation Therapy")
        assert "error" not in result

        members = [m["name"] for m in result["members"]]
        assert len(members) >= 4, f"Anticoagulation should have 4+ members, got: {members}"
        assert "Warfarin" in members
        assert len(result["internal_relationships"]) >= 2, \
            "Should have internal relationships between community members"

    async def test_graph_similarity_finds_structurally_similar_drugs(self):
        """Graph structure reveals similar drugs better than embedding distance alone."""
        from src.graph import find_similar_by_graph

        results = await find_similar_by_graph("Warfarin", strategy="shared_neighbors", limit=5)
        names = [r["name"] for r in results]

        # Aspirin/Clopidogrel should be structurally most similar (both anticoagulant-related)
        assert "Aspirin" in names or "Clopidogrel" in names, \
            f"Expected anticoagulant-related drugs as most similar, got: {names}"

    async def test_multi_hop_reveals_indirect_connections(self):
        """Two-hop traversal finds connections invisible to single-doc RAG."""
        from src.graph import get_neighbors

        # 1-hop from Warfarin
        one_hop = await get_neighbors("Warfarin", depth=1)
        one_hop_names = {r["name"] for r in one_hop}

        # 2-hop from Warfarin
        two_hop = await get_neighbors("Warfarin", depth=2)
        two_hop_names = {r["name"] for r in two_hop}

        # 2-hop should discover nodes not in 1-hop
        new_discoveries = two_hop_names - one_hop_names
        assert len(new_discoveries) > 0, \
            "Two-hop traversal should discover new nodes beyond one-hop"

    async def test_rag_only_misses_interaction_context(self):
        """RAG-only search for Warfarin returns the drug but NOT its interaction partners."""
        from src.tools import _embed
        from src.search import hybrid_search

        embedding = _embed("Warfarin blood thinner")
        rag_results = await hybrid_search("Warfarin", embedding, limit=5)
        rag_names = [r["name"] for r in rag_results]

        # RAG finds Warfarin itself and maybe related concepts
        assert "Warfarin" in rag_names

        # But RAG alone doesn't tell you WHICH drugs interact with Warfarin
        # Graph traversal does:
        from src.graph import get_neighbors
        graph_results = await get_neighbors("Warfarin", relationship_type="INTERACTS_WITH")
        interaction_partners = [r["name"] for r in graph_results]

        # The graph finds specific interaction partners that RAG doesn't surface
        graph_only_findings = set(interaction_partners) - set(rag_names)
        assert len(graph_only_findings) > 0, \
            f"Graph should find interaction partners not in RAG top-5: graph={interaction_partners}, rag={rag_names}"
