-- Create the biomedical knowledge graph in AGE
SET search_path = ag_catalog, "$user", public;

SELECT create_graph('biomedical');
