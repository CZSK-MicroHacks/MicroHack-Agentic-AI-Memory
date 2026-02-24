# Challenge 07: Knowledge Graph — Biomedical Drug Interactions

A GraphRAG-inspired knowledge graph demo using **Biomedical Drug Interactions** as the domain. Demonstrates how graph-based agentic search (traversal, community expansion, shared connections) outperforms plain RAG (semantic + keyword search) for complex, relationship-heavy queries.

## Architecture

```
PostgreSQL (single container)
├── pgvector extension      → semantic search (cosine similarity)
├── tsvector / GIN index    → full-text keyword search
└── Apache AGE extension    → graph structure (Cypher queries)

             ┌─────────────────────────────────────┐
             │          nodes table                 │
             │  id, node_type, name, description,   │
             │  properties, embedding, search_text  │
             └─────────────────────────────────────┘
                          ▲
                          │ linked via name/UUID
                          ▼
             ┌─────────────────────────────────────┐
             │      AGE "biomedical" graph          │
             │  66 vertices, 196 edges              │
             │  Cypher queries for traversal        │
             └─────────────────────────────────────┘
```

### Dual Storage Strategy

1. **Nodes Table** — all entities and concepts stored with vector embeddings (1536-dim, `text-embedding-3-large`) and auto-generated tsvector for full-text search. This is the entry point for queries via hybrid search.

2. **AGE Graph** — the same entities exist as graph vertices, connected by typed, directed edges. Graph traversal (Cypher) reveals relationships, shared connections, and community structure that flat search cannot surface.

## Domain: Biomedical Drug Interactions

### Entity Types (single `nodes` table with `node_type` discriminator)

| node_type | Count | Examples |
|-----------|-------|----------|
| `drug`    | 15    | Warfarin, Metformin, Lisinopril, Sertraline, Ibuprofen |
| `disease` | 12    | Type 2 Diabetes, Hypertension, Rheumatoid Arthritis |
| `gene`    | 10    | CYP2D6, VKORC1, ACE, AMPK, COX-2 |
| `symptom` | 12    | Headache, Fatigue, Nausea, Bleeding |
| `pathway` | 8     | Coagulation Cascade, Serotonin Pathway, Insulin Signaling |
| `concept` | 9     | Cardiovascular Treatments, Diabetes Management, Drug Interaction Risk Factors |

### Relationship Types (~141 edges + 55 community memberships)

| Relationship | Direction | Example |
|---|---|---|
| `TREATS` | drug → disease | Metformin → Type 2 Diabetes |
| `CAUSES_SIDE_EFFECT` | drug → symptom | Warfarin → Bleeding |
| `TARGETS_GENE` | drug → gene | Warfarin → VKORC1 |
| `INTERACTS_WITH` | drug → drug | Warfarin → Aspirin |
| `ASSOCIATED_WITH` | disease → gene | Hypertension → ACE |
| `PRESENTS_AS` | disease → symptom | Diabetes → Fatigue |
| `INVOLVES_PATHWAY` | drug → pathway | Lisinopril → Renin-Angiotensin System |
| `PART_OF_PATHWAY` | gene → pathway | ACE → Renin-Angiotensin System |
| `CONTRAINDICATED` | drug → disease | NSAIDs → Heart Failure |
| `BELONGS_TO_COMMUNITY` | entity → concept | Warfarin → Anticoagulation Therapy |

### Higher-Level Concepts (Communities)

Concepts are GraphRAG-style community summaries — LLM-generated descriptions of therapeutic areas that group related entities. They enable **breadth-first** exploration ("What is the cardiovascular landscape?") vs **depth-first** entity search ("What does Warfarin interact with?").

| Concept | Members |
|---------|---------|
| Anticoagulation Therapy | Warfarin, Aspirin, Clopidogrel, VKORC1, Coagulation Cascade, ... |
| Diabetes Management | Metformin, Insulin, Type 2 Diabetes, AMPK, ... |
| Drug Interaction Risk Factors | Warfarin, Aspirin, Ibuprofen, CYP2D6, ... |
| Chronic Pain Management | Ibuprofen, Gabapentin, COX-2, Pain Signaling Pathway, ... |
| ... | ... |

## How It Works

### Search Strategies

**Hybrid Search (RAG baseline)** — combines semantic (vector cosine similarity) and keyword (tsvector) search using Reciprocal Rank Fusion (RRF). Good for finding relevant individual nodes, but limited to document-level retrieval.

**Graph-Enhanced Search** — uses hybrid search as a starting point, then applies graph traversal:

| Strategy | Entry Point | Traversal | Use Case |
|----------|-------------|-----------|----------|
| **DFS (Depth-First)** | Entity node from search | Follow edges outward | "What drugs interact with Warfarin?" |
| **BFS (Breadth-First)** | Concept node from search | Expand to all community members | "What's the cardiovascular treatment landscape?" |
| **Shared Connections** | Two entity nodes | Find common neighbors & communities | "What do Metformin and Lisinopril have in common?" |
| **Graph Similarity** | One entity node | Rank by shared neighbor/community count | "What drugs are most similar to Warfarin?" |
| **Multi-hop** | One entity node | 2+ hop traversal | "Could diabetes meds affect bleeding risk?" |

### When Graph Beats RAG

| Question | RAG-only | Graph-enhanced |
|----------|----------|----------------|
| "Patient on Warfarin with headache — safe pain meds?" | Finds Warfarin and headache docs separately | Traverses Warfarin → INTERACTS_WITH → finds Aspirin, Ibuprofen to avoid |
| "What do Metformin and Lisinopril share?" | Returns both drugs' descriptions | Finds shared communities, common genes/pathways, interaction data |
| "Cardiovascular treatment overview" | Returns top-5 similar docs | Expands concept node → all 6+ members with internal relationships |
| "Link between diabetes meds and bleeding?" | Finds diabetes and bleeding docs | Multi-hop: Metformin → genes → pathways → coagulation → Warfarin → Bleeding |

## Agent Tools

The `src/tools.py` module provides these async functions, ready to be wrapped as agent-callable tools:

| Tool | Description | Search Strategy |
|------|-------------|-----------------|
| `search_entities(query, node_type?, limit?)` | Hybrid search on entity nodes | DFS entry point |
| `search_concepts(query, limit?)` | Hybrid search on concept/community nodes | BFS entry point |
| `find_related(node_name, relationship_type?, depth?)` | Graph traversal from a node | DFS |
| `tool_expand_concept(concept_name)` | Get all community members + internal relationships | BFS |
| `tool_find_shared_connections(node1, node2)` | Find common neighbors and communities | Cross-reference |
| `tool_find_similar_by_graph(node_name, strategy?, limit?)` | Find structurally similar nodes | Graph analysis |

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Azure OpenAI resource with `gpt-4o-mini` and `text-embedding-3-large` deployments

### 1. Start PostgreSQL (pgvector + AGE)

```bash
cd knowledge-graph
docker compose up -d
```

This builds a custom Docker image with PostgreSQL 16 + pgvector + Apache AGE and initializes the schema automatically.

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Azure OpenAI endpoint
```

### 3. Install Dependencies

```bash
uv sync
```

### 4. Generate & Load Data

```bash
cd scripts

# Generate entities, relationships, and concepts using LLM
uv run python generate_entities.py
uv run python generate_relationships.py
uv run python supplement_relationships.py
uv run python generate_concepts.py

# Load into PostgreSQL (computes embeddings + populates AGE graph)
uv run python load_nodes.py
uv run python load_graph.py
```

### 5. Run Tests

```bash
cd ..
uv run python -m pytest tests/ -v
```

Expected: 31 tests passing across search, graph, tools, and comparison test files.

### 6. Run the Comparison Demo

```bash
uv run python comparison_demo.py
```

Shows side-by-side RAG-only vs graph-enhanced results for 5 curated questions.

### 7. Run the Interactive Agent

```bash
uv run python agent.py
```

Type questions or `examples` to see sample queries. The agent uses hybrid search + graph traversal + LLM to generate comprehensive answers.

## File Structure

```
knowledge-graph/
├── docker-compose.yml          # PG16 + pgvector + AGE container
├── Dockerfile                  # Custom image building AGE from source
├── pyproject.toml              # Python dependencies
├── .env.example                # Config template
├── init/
│   ├── 001_extensions.sql      # CREATE EXTENSION vector, age
│   ├── 002_nodes_table.sql     # nodes table + indexes
│   └── 003_age_graph.sql       # CREATE graph 'biomedical'
├── scripts/
│   ├── helpers.py              # Shared: OpenAI client, embeddings, JSON I/O
│   ├── generate_entities.py    # LLM generates 57 biomedical entities
│   ├── generate_relationships.py   # LLM generates initial relationships
│   ├── supplement_relationships.py # Adds more edges in targeted batches
│   ├── generate_concepts.py    # LLM generates 9 community/concept nodes
│   ├── load_nodes.py           # Compute embeddings, insert into nodes table
│   └── load_graph.py           # Create AGE vertices + edges + community links
├── src/
│   ├── db.py                   # Async PG pool (auto-recreates per event loop)
│   ├── search.py               # semantic_search, keyword_search, hybrid_search (RRF)
│   ├── graph.py                # AGE Cypher: neighbors, shared, expand, similar
│   └── tools.py                # Agent tools wrapping search + graph
├── tests/
│   ├── test_search.py          # 7 tests: semantic, keyword, hybrid
│   ├── test_graph.py           # 8 tests: neighbors, shared, expand, similar
│   ├── test_tools.py           # 10 tests: all tool functions
│   └── test_comparison.py      # 6 tests: graph search beats RAG
├── data/                       # Generated JSON (entities, relationships, concepts)
├── agent.py                    # Interactive CLI agent
├── comparison_demo.py          # Side-by-side RAG vs Graph demo
└── README.md                   # This file
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Single `nodes` table with `node_type` column | Simpler indexing, uniform hybrid search, one set of indexes to maintain |
| HNSW index (not IVFFlat) | pgvector's IVFFlat caps at 2000 dims; HNSW supports our 1536-dim vectors |
| 1536-dim embeddings | `text-embedding-3-large` supports dimension reduction; 1536 fits pgvector index limits while retaining quality |
| Apache AGE for graph | Cypher queries, runs in-process with PG (no separate graph DB), ACID guarantees |
| LLM-generated data | Reproducible, realistic; makes the lab self-contained |
| Pool per event-loop | Prevents stale connection errors when pytest creates new event loops per test |

## Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Database | PostgreSQL 16 | Unified store |
| Vector search | pgvector (HNSW) | Semantic similarity |
| Full-text search | tsvector + GIN | Keyword matching |
| Graph engine | Apache AGE 1.5.0 | Cypher traversal |
| Embeddings | Azure OpenAI `text-embedding-3-large` | 1536-dim vectors |
| LLM | Azure OpenAI `gpt-4o-mini` | Data generation, agent reasoning |
| Runtime | Python 3.11+ (asyncpg) | Async database access |
| Container | Docker Compose | Local development |
