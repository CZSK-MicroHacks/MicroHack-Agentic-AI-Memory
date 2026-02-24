"""
Generate relationships between biomedical entities using Azure OpenAI.

Reads: data/entities.json
Output: data/relationships.json
"""

import logging

from helpers import get_openai_client, chat_json, save_json, load_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kg.generate_relationships")

SYSTEM_PROMPT = """\
You are a biomedical knowledge expert. Given a list of biomedical entities, generate realistic relationships between them for a knowledge graph.

Return a JSON object with a single key "relationships" containing an array of relationship objects.
Each relationship must have:
- "source": the name of the source entity (must match an entity name exactly)
- "target": the name of the target entity (must match an entity name exactly)
- "relationship_type": one of the following:
  - "treats" (drug → disease)
  - "causes_side_effect" (drug → symptom)
  - "targets_gene" (drug → gene)
  - "interacts_with" (drug → drug): drug-drug interactions
  - "associated_with" (disease → gene)
  - "presents_as" (disease → symptom)
  - "involves_pathway" (drug → pathway)
  - "part_of_pathway" (gene → pathway)
  - "contraindicated" (drug → disease): drug should NOT be used for this condition
- "properties": an object with:
  - "strength": "strong"|"moderate"|"weak" — strength of the relationship
  - "evidence": "well-established"|"emerging"|"theoretical" — evidence level
  - "description": a brief description of why this relationship exists

IMPORTANT guidelines:
1. Create a DENSE graph: each entity should have at least 2-3 relationships
2. Include drug-drug interactions (interacts_with) — these are crucial for graph search demo
3. Create overlapping symptom-disease links (same symptom for multiple diseases)
4. Link multiple drugs to the same pathways and genes to create shared connections
5. Include some contraindications
6. Make the graph rich enough that traversal reveals non-obvious connections
7. Aim for 150-200 relationships total
"""


def main():
    logger.info("Generating relationships...")
    client = get_openai_client()
    entities = load_json("entities.json")

    # Format entity list for the prompt
    entity_list = "\n".join(
        f"- [{e['node_type']}] {e['name']}"
        for e in entities
    )

    user_prompt = f"""\
Here are the entities in our knowledge graph:

{entity_list}

Generate 150-200 realistic biomedical relationships between these entities.
Ensure dense connectivity — every entity should participate in at least 2 relationships.
Pay special attention to:
- Drug-drug interactions (interacts_with): at least 15 pairs
- Shared symptoms across diseases: at least 20 presents_as relationships
- Gene-pathway connections: every gene should be part of at least 1 pathway
- Drug-pathway connections: at least 10 involves_pathway relationships

Return the JSON object with the "relationships" array.
"""

    result = chat_json(client, SYSTEM_PROMPT, user_prompt, temperature=0.7)
    relationships = result.get("relationships", [])

    logger.info("Generated %d relationships", len(relationships))

    # Log type distribution
    from collections import Counter
    dist = Counter(r["relationship_type"] for r in relationships)
    for t, c in sorted(dist.items()):
        logger.info("  %s: %d", t, c)

    # Validate entity references
    entity_names = {e["name"] for e in entities}
    invalid = []
    for r in relationships:
        if r["source"] not in entity_names:
            invalid.append(f"Unknown source: {r['source']}")
        if r["target"] not in entity_names:
            invalid.append(f"Unknown target: {r['target']}")
    if invalid:
        logger.warning("Found %d invalid references:", len(invalid))
        for msg in invalid[:10]:
            logger.warning("  %s", msg)

    save_json(relationships, "relationships.json")
    logger.info("Done! Saved to data/relationships.json")


if __name__ == "__main__":
    main()
