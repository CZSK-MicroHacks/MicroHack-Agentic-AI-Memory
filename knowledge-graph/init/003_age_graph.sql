-- Reset and recreate the AGE graph used for graph traversal.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM ag_catalog.ag_graph
        WHERE name = 'biomedical'
    ) THEN
        PERFORM ag_catalog.drop_graph('biomedical', true);
    END IF;

    PERFORM ag_catalog.create_graph('biomedical');
END
$$;
