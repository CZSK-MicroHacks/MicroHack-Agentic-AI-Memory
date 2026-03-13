-- Reset and recreate the nodes table used for hybrid search.
DROP TABLE IF EXISTS public.nodes CASCADE;

CREATE TABLE public.nodes (
    id              UUID PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    node_type       TEXT         NOT NULL,   -- drug, disease, gene, symptom, pathway, concept
    name            TEXT         NOT NULL,
    description     TEXT         NOT NULL,
    properties      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(1536) NOT NULL,   -- text-embedding-3-large reduced to 1536 dims
    search_text     tsvector GENERATED ALWAYS AS (
        to_tsvector('english', name || ' ' || description)
    ) STORED,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_node_type_name UNIQUE (node_type, name)
);

CREATE INDEX idx_nodes_embedding
    ON public.nodes USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_nodes_search_text
    ON public.nodes USING GIN (search_text);

CREATE INDEX idx_nodes_type
    ON public.nodes (node_type);
