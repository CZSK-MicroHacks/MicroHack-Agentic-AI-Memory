#!/usr/bin/env python3
"""
setup_search.py — One-time script to set up Azure AI Search for the RAG feature.

Creates:
  1. Two search indexes: "orders" and "return-policy"
  2. Uploads documents with embeddings to both indexes
  3. Two knowledge sources wrapping the indexes
  4. One knowledge base aggregating both sources (extractive data, minimal reasoning)

Usage:
    cd setup/knowledgebase
    pip install -r requirements.txt
    python setup_search.py

Environment variables (from .env or exported):
    AZURE_SEARCH_ENDPOINT          — AI Search endpoint (e.g. https://search-mhaimem.search.windows.net)
    AZURE_OPENAI_ENDPOINT          — Azure OpenAI endpoint
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME — Embedding model deployment (default: text-embedding-3-large)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchField,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AzureOpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv
    # Look for .env in project root (two levels up from this script)
    env_path = Path(__file__).resolve().parents[2] / "backend" / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)
except ImportError:
    pass

SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large")
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 3072

ORDERS_INDEX = os.getenv("AZURE_SEARCH_ORDERS_INDEX", "orders")
POLICIES_INDEX = os.getenv("AZURE_SEARCH_POLICIES_INDEX", "return-policy")
KB_NAME = os.getenv("AZURE_SEARCH_KNOWLEDGE_BASE_NAME", "customer-support-kb")

DOCUMENTS_DIR = Path(__file__).resolve().parent / "documents"

credential = DefaultAzureCredential()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_openai_client() -> AzureOpenAI:
    """Create a sync Azure OpenAI client for embedding generation."""
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    return AzureOpenAI(
        azure_endpoint=OPENAI_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version="2024-06-01",
    )


def embed_texts(client: AzureOpenAI, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    response = client.embeddings.create(model=EMBEDDING_DEPLOYMENT, input=texts)
    return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Step 1: Create Indexes
# ---------------------------------------------------------------------------

def create_orders_index(index_client: SearchIndexClient) -> None:
    """Create the orders search index."""
    index = SearchIndex(
        name=ORDERS_INDEX,
        fields=[
            SearchField(name="id", type="Edm.String", key=True, filterable=True, sortable=True),
            SearchField(name="order_id", type="Edm.String", filterable=True, sortable=True, facetable=True),
            SearchField(name="category", type="Edm.String", filterable=True, facetable=True),
            SearchField(
                name="page_chunk",
                type="Edm.String",
                searchable=True,
                filterable=False,
                sortable=False,
            ),
            SearchField(
                name="page_embedding",
                type="Collection(Edm.Single)",
                stored=False,
                vector_search_dimensions=EMBEDDING_DIMS,
                vector_search_profile_name="hnsw_text_3_large",
            ),
        ],
        vector_search=VectorSearch(
            profiles=[
                VectorSearchProfile(
                    name="hnsw_text_3_large",
                    algorithm_configuration_name="alg",
                    vectorizer_name="azure_openai_text_3_large",
                )
            ],
            algorithms=[HnswAlgorithmConfiguration(name="alg")],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="azure_openai_text_3_large",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=OPENAI_ENDPOINT,
                        deployment_name=EMBEDDING_DEPLOYMENT,
                        model_name=EMBEDDING_MODEL,
                    ),
                )
            ],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="semantic_config",
            configurations=[
                SemanticConfiguration(
                    name="semantic_config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="page_chunk")]
                    ),
                )
            ],
        ),
    )
    index_client.create_or_update_index(index)
    print(f"  ✅ Index '{ORDERS_INDEX}' created/updated")


def create_policies_index(index_client: SearchIndexClient) -> None:
    """Create the return-policy search index."""
    index = SearchIndex(
        name=POLICIES_INDEX,
        fields=[
            SearchField(name="id", type="Edm.String", key=True, filterable=True, sortable=True),
            SearchField(name="section", type="Edm.String", filterable=True, facetable=True),
            SearchField(
                name="page_chunk",
                type="Edm.String",
                searchable=True,
                filterable=False,
                sortable=False,
            ),
            SearchField(
                name="page_embedding",
                type="Collection(Edm.Single)",
                stored=False,
                vector_search_dimensions=EMBEDDING_DIMS,
                vector_search_profile_name="hnsw_text_3_large",
            ),
        ],
        vector_search=VectorSearch(
            profiles=[
                VectorSearchProfile(
                    name="hnsw_text_3_large",
                    algorithm_configuration_name="alg",
                    vectorizer_name="azure_openai_text_3_large",
                )
            ],
            algorithms=[HnswAlgorithmConfiguration(name="alg")],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="azure_openai_text_3_large",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=OPENAI_ENDPOINT,
                        deployment_name=EMBEDDING_DEPLOYMENT,
                        model_name=EMBEDDING_MODEL,
                    ),
                )
            ],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="semantic_config",
            configurations=[
                SemanticConfiguration(
                    name="semantic_config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="page_chunk")]
                    ),
                )
            ],
        ),
    )
    index_client.create_or_update_index(index)
    print(f"  ✅ Index '{POLICIES_INDEX}' created/updated")


# ---------------------------------------------------------------------------
# Step 2: Upload Documents
# ---------------------------------------------------------------------------

def upload_documents(
    index_name: str,
    docs_dir: Path,
    openai_client: AzureOpenAI,
) -> int:
    """Load JSON docs from a directory, compute embeddings, upload to index."""
    all_docs: list[dict] = []
    for json_file in sorted(docs_dir.glob("*.json")):
        with open(json_file) as f:
            file_docs = json.load(f)
        all_docs.extend(file_docs)

    if not all_docs:
        print(f"  ⚠️  No documents found in {docs_dir}")
        return 0

    # Generate embeddings for all chunks
    texts = [doc["page_chunk"] for doc in all_docs]
    print(f"  Generating embeddings for {len(texts)} documents...")
    embeddings = embed_texts(openai_client, texts)

    # Attach embeddings to documents
    for doc, emb in zip(all_docs, embeddings):
        doc["page_embedding"] = emb

    # Upload to index (use stable API version for data operations)
    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=index_name,
        credential=credential,
        api_version="2024-07-01",
    )
    results = search_client.upload_documents(documents=all_docs)
    failed = [r for r in results if not r.succeeded]
    if failed:
        for r in failed:
            print(f"    ❌ key={r.key} status={r.status_code} error={r.error_message}")
        raise RuntimeError(f"{len(failed)} document(s) failed to upload")

    print(f"  ✅ Uploaded {len(all_docs)} documents to '{index_name}'")
    return len(all_docs)


# ---------------------------------------------------------------------------
# Step 3: Create Knowledge Sources & Knowledge Base
# ---------------------------------------------------------------------------

def create_knowledge_sources_and_base(index_client: SearchIndexClient) -> None:
    """Create knowledge sources and knowledge base using the REST API via SDK."""
    from azure.search.documents.indexes.models import (
        SearchIndexKnowledgeSource,
        SearchIndexKnowledgeSourceParameters,
        SearchIndexFieldReference,
        KnowledgeBase,
        KnowledgeSourceReference,
        KnowledgeRetrievalOutputMode,
        KnowledgeRetrievalMinimalReasoningEffort,
    )

    # Knowledge Source: Orders
    orders_ks = SearchIndexKnowledgeSource(
        name="orders-knowledge-source",
        description="Detailed order information including products, shipping, and payment details",
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=ORDERS_INDEX,
            source_data_fields=[
                SearchIndexFieldReference(name="id"),
                SearchIndexFieldReference(name="order_id"),
                SearchIndexFieldReference(name="category"),
            ],
        ),
    )
    index_client.create_or_update_knowledge_source(knowledge_source=orders_ks)
    print(f"  ✅ Knowledge source 'orders-knowledge-source' created/updated")

    # Knowledge Source: Policies
    policies_ks = SearchIndexKnowledgeSource(
        name="policies-knowledge-source",
        description="Company return and refund policies, eligibility rules, and process steps",
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=POLICIES_INDEX,
            source_data_fields=[
                SearchIndexFieldReference(name="id"),
                SearchIndexFieldReference(name="section"),
            ],
        ),
    )
    index_client.create_or_update_knowledge_source(knowledge_source=policies_ks)
    print(f"  ✅ Knowledge source 'policies-knowledge-source' created/updated")

    # Knowledge Base
    kb = KnowledgeBase(
        name=KB_NAME,
        knowledge_sources=[
            KnowledgeSourceReference(name="orders-knowledge-source"),
            KnowledgeSourceReference(name="policies-knowledge-source"),
        ],
        output_mode=KnowledgeRetrievalOutputMode.EXTRACTIVE_DATA,
        retrieval_reasoning_effort=KnowledgeRetrievalMinimalReasoningEffort(),
    )
    index_client.create_or_update_knowledge_base(knowledge_base=kb)
    print(f"  ✅ Knowledge base '{KB_NAME}' created/updated")

    mcp_endpoint = f"{SEARCH_ENDPOINT}/knowledgebases/{KB_NAME}/mcp?api-version=2025-11-01-Preview"
    print(f"\n  MCP endpoint: {mcp_endpoint}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  AI Search Knowledgebase Setup                             ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    print(f"  Search endpoint:      {SEARCH_ENDPOINT}")
    print(f"  OpenAI endpoint:      {OPENAI_ENDPOINT}")
    print(f"  Embedding deployment: {EMBEDDING_DEPLOYMENT}")
    print(f"  Embedding dimensions: {EMBEDDING_DIMS}")
    print(f"  Knowledge base name:  {KB_NAME}")
    print()

    index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)
    openai_client = create_openai_client()

    # Step 1: Create indexes
    print("Step 1: Creating search indexes...")
    create_orders_index(index_client)
    create_policies_index(index_client)

    # Brief pause between index creation and upload
    print("\n  Waiting 5s for indexes to be ready...")
    time.sleep(5)

    # Step 2: Upload documents
    print("\nStep 2: Uploading documents...")
    orders_dir = DOCUMENTS_DIR / "orders"
    policies_dir = DOCUMENTS_DIR / "policies"
    n_orders = upload_documents(ORDERS_INDEX, orders_dir, openai_client)
    n_policies = upload_documents(POLICIES_INDEX, policies_dir, openai_client)
    print(f"\n  Total: {n_orders + n_policies} documents uploaded")

    # Brief pause to let indexing complete
    print("\n  Waiting 10s for indexing to settle...")
    time.sleep(10)

    # Step 3: Create knowledge sources and knowledge base
    print("\nStep 3: Creating knowledge sources and knowledge base...")
    create_knowledge_sources_and_base(index_client)

    print("\n✅ Setup complete!")


if __name__ == "__main__":
    main()
