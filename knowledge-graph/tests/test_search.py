"""
Tests for hybrid search on the nodes table.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="module")
def embedding():
    """Get a real embedding for test queries."""
    from src.tools import _embed
    return _embed("heart disease cardiovascular treatment")


@pytest.fixture(scope="module")
def pain_embedding():
    from src.tools import _embed
    return _embed("pain relief anti-inflammatory medication")


class TestSemanticSearch:
    @pytest.mark.asyncio
    async def test_finds_relevant_nodes(self, embedding):
        from src.search import semantic_search
        results = await semantic_search(embedding, limit=5)
        assert len(results) > 0
        names = [r["name"] for r in results]
        # Should find cardiovascular-related entities
        assert any(
            term in name.lower()
            for name in names
            for term in ["heart", "cardio", "hypertension", "atorvastatin", "lisinopril"]
        ), f"Expected cardiovascular entities, got: {names}"

    @pytest.mark.asyncio
    async def test_filters_by_node_type(self, embedding):
        from src.search import semantic_search
        results = await semantic_search(embedding, node_type="drug", limit=5)
        assert len(results) > 0
        assert all(r["node_type"] == "drug" for r in results)

    @pytest.mark.asyncio
    async def test_concept_search(self):
        from src.tools import _embed
        from src.search import semantic_search
        emb = _embed("diabetes insulin blood sugar management")
        results = await semantic_search(emb, node_type="concept", limit=3)
        assert len(results) > 0
        names = [r["name"] for r in results]
        assert any("diabet" in n.lower() for n in names), f"Expected diabetes concept, got: {names}"


class TestKeywordSearch:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        from src.search import keyword_search
        results = await keyword_search("Warfarin", limit=5)
        assert len(results) > 0
        assert any(r["name"] == "Warfarin" for r in results)

    @pytest.mark.asyncio
    async def test_disease_keyword(self):
        from src.search import keyword_search
        results = await keyword_search("diabetes", node_type="disease", limit=5)
        assert len(results) > 0
        assert all(r["node_type"] == "disease" for r in results)


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_combines_both_methods(self, embedding):
        from src.search import hybrid_search
        results = await hybrid_search("heart disease", embedding, limit=5)
        assert len(results) > 0
        # Should have RRF score
        assert all("rrf_score" in r for r in results)

    @pytest.mark.asyncio
    async def test_pain_medications(self, pain_embedding):
        from src.search import hybrid_search
        results = await hybrid_search("pain relief medication", pain_embedding, node_type="drug", limit=5)
        assert len(results) > 0
        names = [r["name"] for r in results]
        assert any(
            n in names for n in ["Ibuprofen", "Aspirin", "Gabapentin"]
        ), f"Expected pain meds, got: {names}"
