-- Nodes table: unified store for all entity types with hybrid search support
CREATE TABLE IF NOT EXISTS nodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_type       TEXT         NOT NULL,   -- drug, disease, gene, symptom, pathway, concept
    name            TEXT         NOT NULL,
    description     TEXT         NOT NULL,
    properties      JSONB        DEFAULT '{}',
    embedding       vector(1536) NOT NULL,   -- text-embedding-3-large (reduced to 1536 dims)
    search_text     tsvector GENERATED ALWAYS AS (
        to_tsvector('english', name || ' ' || description)
    ) STORED,
    created_at      TIMESTAMPTZ  DEFAULT now(),

    CONSTRAINT uq_node_type_name UNIQUE (node_type, name)
);

-- Semantic search (cosine similarity) — HNSW supports 3072 dims (ivfflat caps at 2000)
CREATE INDEX IF NOT EXISTS idx_nodes_embedding
    ON nodes USING hnsw (embedding vector_cosine_ops);

-- Full-text search (GIN inverted index)
CREATE INDEX IF NOT EXISTS idx_nodes_search_text
    ON nodes USING GIN (search_text);

-- Filter by type
CREATE INDEX IF NOT EXISTS idx_nodes_type
    ON nodes (node_type);
