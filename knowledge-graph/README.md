# Challenge 07: Knowledge Graph — Biomedical Drug Interactions

A GraphRAG-inspired knowledge graph demo using **Biomedical Drug Interactions** as the domain. Demonstrates how graph-based agentic search (traversal, community expansion, shared connections) outperforms plain RAG (semantic + keyword search) for complex, relationship-heavy queries.

## Architecture

```
Azure Database for PostgreSQL Flexible Server (PG 16)
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
             │  66 vertices, 234 edges              │
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

### Relationship Types (~179 edges + 55 community memberships = 234 total)

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

## Truly Agentic Architecture

The agent (`agent.py`) uses **OpenAI function-calling** — the LLM autonomously decides which tools to invoke and in what order. There is no hardcoded pipeline; the agent reasons about the question and picks the right sequence of tool calls.

### Agent Tools (Function-Calling Schema)

| Tool | Description | Search Strategy |
|------|-------------|-----------------|
| `search_entities(query, node_type?, limit?)` | Hybrid search on entity nodes | DFS entry point |
| `search_concepts(query, limit?)` | Hybrid search on concept/community nodes | BFS entry point |
| `find_related(node_name, relationship_type?, depth?)` | Graph traversal from a node | DFS |
| `expand_concept(concept_name)` | Get all community members + internal relationships | BFS |
| `find_shared_connections(node1, node2)` | Find common neighbors and communities | Cross-reference |
| `find_similar_by_graph(node_name, strategy?, limit?)` | Find structurally similar nodes | Graph analysis |

### How the Agent Decides

The LLM receives tool schemas and a system prompt. For each question it:
1. Decides which tool(s) to call (may call multiple in sequence)
2. Receives tool results as assistant messages
3. Decides whether to call more tools or generate a final answer
4. Repeats up to 8 iterations (configurable)

**Example: "A patient on Warfarin has a headache — safe pain meds?"**
```
🔧 find_related(node_name='Warfarin', relationship_type='INTERACTS_WITH')
   → 7 results: Amoxicillin, Aspirin, Clopidogrel, Ibuprofen, ...
🤖 "Patients on Warfarin should avoid Aspirin and Ibuprofen..."
```

**Example: "What is the cardiovascular treatment landscape?"**
```
🔧 search_concepts(query='Cardiovascular Treatments')
   → 3 results: Cardiovascular Disease Management, Anticoagulation Therapy, ...
🔧 expand_concept(concept_name='Cardiovascular Disease Management')
   → 6 members: Heart Failure, Hypertension, Atorvastatin, Lisinopril, ...
🔧 expand_concept(concept_name='Anticoagulation Therapy')
   → 6 members: Warfarin, Clopidogrel, Atrial Fibrillation, ...
🔧 expand_concept(concept_name='Shared Metabolic Pathways')
   → 7 members: Atorvastatin, Insulin, Metformin, AMPK, ...
🤖 Comprehensive answer covering all 3 communities with internal relationships
```

The agent's tool call trace is displayed in both the interactive agent and the comparison demo.

## Quick Start

### Prerequisites
- Azure subscription with deployed infrastructure (see `infra/` Terraform)
- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Azure OpenAI resource with `gpt-4o-mini` and `text-embedding-3-large` deployments
- Azure Database for PostgreSQL Flexible Server with AGE and pgvector extensions enabled

### 1. Azure PostgreSQL Setup

The PostgreSQL Flexible Server is deployed via Terraform in the `infra/` directory with:
- `azure.extensions`: AGE, VECTOR
- `shared_preload_libraries`: age
- Firewall rules for Azure services and your client IP

Ensure the server is running:
```bash
az postgres flexible-server start --name <server-name> --resource-group <rg-name>
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Azure PostgreSQL and OpenAI endpoints
```

### 3. Install Dependencies

```bash
uv sync
```

### 4. Initialize Database Schema

Connect to Azure PostgreSQL and run the init scripts:
```bash
# Using psql or any PostgreSQL client against your Azure endpoint
psql "host=<server>.postgres.database.azure.com port=5432 dbname=appdb user=pgadmin sslmode=require" -f init/001_extensions.sql
psql "host=<server>.postgres.database.azure.com port=5432 dbname=appdb user=pgadmin sslmode=require" -f init/002_nodes_table.sql
psql "host=<server>.postgres.database.azure.com port=5432 dbname=appdb user=pgadmin sslmode=require" -f init/003_age_graph.sql
```

### 5. Generate & Load Data

```bash
cd scripts

# Generate entities, relationships (with enrichment), and concepts using LLM
uv run python generate_entities.py
uv run python generate_relationships.py   # Phase 1: initial + Phase 2: enrichment batches
uv run python generate_concepts.py

# Load into Azure PostgreSQL (computes embeddings + populates AGE graph)
uv run python load_nodes.py
uv run python load_graph.py
```

### 6. Run Tests

```bash
cd ..
uv run python -m pytest tests/ -v
```

Expected: 31 tests passing across search, graph, tools, and comparison test files.

### 7. Run the Comparison Demo

```bash
uv run python comparison_demo.py
```

Shows 5 curated questions answered by RAG-only (single hybrid search) vs the agentic graph agent (LLM-driven multi-tool exploration). Each question includes tool call traces showing how the agent autonomously decided what to search and traverse.

### 8. Run the Interactive Agent

```bash
uv run python agent.py
```

Type questions or `examples` to see sample queries. The agent uses **OpenAI function-calling** to autonomously decide which tools to invoke — it discovers relationships, expands communities, and finds shared connections without being told which edges to follow.

### 9. Run the Graphical Comparison Demo (Web UI)

```bash
# Build the frontend (one-time)
cd web && npm install && npm run build && npm run dev

# Start the API server (serves both API and frontend)
uv run python api_server.py
```

Open http://localhost:8080 in your browser. Select any of the 5 curated questions to see a side-by-side comparison of RAG-only vs agentic graph search, complete with tool call traces.

![](/images/knowledge-graph.png)

## File Structure

```
knowledge-graph/
├── pyproject.toml              # Python dependencies
├── .env.example                # Config template
├── init/
│   ├── 001_extensions.sql      # CREATE EXTENSION vector, age
│   ├── 002_nodes_table.sql     # nodes table + indexes
│   └── 003_age_graph.sql       # CREATE graph 'biomedical'
├── scripts/
│   ├── helpers.py              # Shared: OpenAI client, embeddings, JSON I/O
│   ├── generate_entities.py    # LLM generates 57 biomedical entities
│   ├── generate_relationships.py   # LLM generates relationships (Phase 1 + Phase 2 enrichment)
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
├── agent.py                    # Truly agentic CLI (OpenAI function-calling loop)
├── comparison_demo.py          # RAG-only vs agentic graph side-by-side demo (CLI)
├── api_server.py               # FastAPI backend for graphical comparison demo
├── web/                        # React + Tailwind frontend for graphical demo
└── README.md                   # This file
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Single `nodes` table with `node_type` column | Simpler indexing, uniform hybrid search, one set of indexes to maintain |
| HNSW index (not IVFFlat) | pgvector's IVFFlat caps at 2000 dims; HNSW supports our 1536-dim vectors |
| 1536-dim embeddings | `text-embedding-3-large` supports dimension reduction; 1536 fits pgvector index limits while retaining quality |
| Apache AGE for graph | Cypher queries, runs in-process with PG (no separate graph DB), ACID guarantees |
| Azure Database for PostgreSQL | Managed service with native support for pgvector and AGE extensions |
| LLM-generated data | Reproducible, realistic; makes the lab self-contained |
| Pool per event-loop | Prevents stale connection errors when pytest creates new event loops per test |

## Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Database | Azure Database for PostgreSQL Flexible Server (PG 16) | Unified managed store |
| Vector search | pgvector (HNSW) | Semantic similarity |
| Full-text search | tsvector + GIN | Keyword matching |
| Graph engine | Apache AGE 1.6.0 | Cypher traversal |
| Embeddings | Azure OpenAI `text-embedding-3-large` | 1536-dim vectors |
| LLM | Azure OpenAI `gpt-4o-mini` | Data generation, agent reasoning |
| Runtime | Python 3.11+ (asyncpg) | Async database access |
| Infrastructure | Terraform | Azure resource provisioning |
