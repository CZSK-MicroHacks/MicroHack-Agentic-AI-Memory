-- Create the biomedical knowledge graph in AGE
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

SELECT create_graph('biomedical');
