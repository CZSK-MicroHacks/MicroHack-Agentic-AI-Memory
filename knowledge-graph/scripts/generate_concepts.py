"""
Generate higher-level concept/community nodes using Azure OpenAI.

Reads: data/entities.json, data/relationships.json
Output: data/concepts.json
"""

import logging

from helpers import get_openai_client, chat_json, save_json, load_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kg.generate_concepts")

SYSTEM_PROMPT = """\
You are a biomedical knowledge expert. Given a knowledge graph of biomedical entities and their relationships, identify higher-level therapeutic/biological concepts (communities) that group related entities together.

These concept nodes represent therapeutic areas, biological systems, or treatment paradigms — similar to communities in GraphRAG. Each concept should:
1. Have a clear, descriptive name
2. Include a comprehensive 3-5 sentence summary describing the therapeutic area, key drugs, conditions, and mechanisms
3. Map to specific entity members (drugs, diseases, genes, symptoms, pathways) that belong to this concept

Return a JSON object with key "concepts" containing an array of concept objects:
- "name": concept name (e.g. "Cardiovascular Treatments")
- "description": a rich 3-5 sentence summary suitable for semantic search. It should describe the therapeutic landscape, key relationships, and clinical significance.
- "members": array of entity names that belong to this concept (must match entity names exactly)
- "properties": {"category": "therapeutic_area"|"biological_system"|"treatment_paradigm"}

IMPORTANT:
- Create 8-10 concepts that cover all entities
- Entities CAN belong to multiple concepts (overlapping communities)
- The descriptions should contain enough detail that semantic search on the concept alone would answer high-level questions about the therapeutic area
- Include cross-cutting concepts like "Drug Interaction Risk Factors" that span multiple therapeutic areas
"""


def main():
    logger.info("Generating concept nodes...")
    client = get_openai_client()

    entities = load_json("entities.json")
    relationships = load_json("relationships.json")

    entity_list = "\n".join(
        f"- [{e['node_type']}] {e['name']}: {e['description'][:100]}..."
        for e in entities
    )

    rel_summary = "\n".join(
        f"- {r['source']} --[{r['relationship_type']}]--> {r['target']}"
        for r in relationships[:80]
    )

    user_prompt = f"""\
Here are the entities in our biomedical knowledge graph:

{entity_list}

Key relationships (sample of {len(relationships)} total):
{rel_summary}

Generate 8-10 higher-level concept/community nodes that group these entities into meaningful therapeutic areas and biological systems. Each entity should belong to at least one concept, and some entities should appear in multiple concepts where clinically relevant.

Include at least one cross-cutting concept like "Drug Interaction Risk Factors" or "Shared Metabolic Pathways" that spans multiple therapeutic areas — these are particularly valuable for demonstrating graph search advantages.

Return the JSON object with the "concepts" array.
"""

    result = chat_json(client, SYSTEM_PROMPT, user_prompt, temperature=0.7)
    concepts = result.get("concepts", [])

    logger.info("Generated %d concepts", len(concepts))

    # Validate member references
    entity_names = {e["name"] for e in entities}
    for concept in concepts:
        valid_members = [m for m in concept["members"] if m in entity_names]
        invalid = [m for m in concept["members"] if m not in entity_names]
        if invalid:
            logger.warning("Concept '%s' has %d invalid members: %s",
                         concept["name"], len(invalid), invalid[:5])
        concept["members"] = valid_members
        logger.info("  %s: %d members", concept["name"], len(valid_members))

    save_json(concepts, "concepts.json")
    logger.info("Done! Saved to data/concepts.json")


if __name__ == "__main__":
    main()
