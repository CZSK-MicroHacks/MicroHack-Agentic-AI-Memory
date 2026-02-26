-- Extensions: pgvector + AGE
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age CASCADE;

-- Make AGE types available without schema prefix
-- Note: LOAD 'age' is not needed when shared_preload_libraries includes 'age'
SET search_path = ag_catalog, "$user", public;
