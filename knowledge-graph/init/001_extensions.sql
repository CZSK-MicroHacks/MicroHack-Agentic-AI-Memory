-- Extensions: pgvector + AGE
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

-- Make AGE types available without schema prefix
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
