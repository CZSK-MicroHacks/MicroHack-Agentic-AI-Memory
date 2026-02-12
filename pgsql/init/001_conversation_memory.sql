-- Conversation Memory schema (pgvector)
-- Stores summarised conversation history items with vector embeddings.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS conversation_memory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT         NOT NULL,
    user_id         TEXT         NOT NULL,
    summary         TEXT         NOT NULL,
    embedding       vector(3072) NOT NULL,   -- text-embedding-3-large
    source_title    TEXT,
    message_count   INT          NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_conversation_memory UNIQUE (conversation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_user
    ON conversation_memory (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_embedding
    ON conversation_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
