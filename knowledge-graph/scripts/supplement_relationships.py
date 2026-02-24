"""
Supplement relationships by generating additional edges in targeted batches.

Reads: data/entities.json, data/relationships.json
Output: data/relationships.json (updated with more relationships)
"""

import logging

from helpers import get_openai_client, chat_json, save_json, load_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kg.supplement_relationships")

SYSTEM_PROMPT = """\
You are a biomedical knowledge expert. Generate additional realistic relationships between biomedical entities.
Return a JSON object with a single key "relationships" containing an array of relationship objects.
Each must have: "source", "target", "relationship_type", "properties" (with "strength", "evidence", "description").
Only use entity names from the provided list. Do NOT duplicate existing relationships.
"""

BATCHES = [
    {
        "focus": "drug-drug interactions",
        "instruction": """Generate 15-20 drug-drug interaction relationships (relationship_type: "interacts_with").
Focus on clinically significant interactions like:
- Warfarin interacting with Aspirin, Ibuprofen, Amoxicillin, Omeprazole, Clopidogrel
- Metformin interacting with Prednisone, Lisinopril
- Sertraline interacting with Ibuprofen, Aspirin, Gabapentin
- Atorvastatin interacting with Omeprazole, Amoxicillin
- Prednisone interacting with Aspirin, Ibuprofen, Methotrexate, Insulin
Include both directions where appropriate (drug A interacts_with drug B)."""
    },
    {
        "focus": "disease-symptom connections",
        "instruction": """Generate 20-25 disease-symptom relationships (relationship_type: "presents_as").
Make symptoms overlap across diseases:
- Fatigue should be linked to at least 5 diseases
- Headache to at least 3 diseases
- Nausea to at least 4 diseases
- Joint Pain to at least 3 diseases
- Shortness of Breath and Swelling to cardiovascular diseases
- Weight Gain to metabolic/endocrine diseases"""
    },
    {
        "focus": "gene-disease associations",
        "instruction": """Generate 15-20 disease-gene associations (relationship_type: "associated_with").
Link genes to diseases they're known to be involved in:
- ACE → Hypertension, Heart Failure
- VKORC1 → Deep Vein Thrombosis, Atrial Fibrillation
- AMPK → Type 2 Diabetes
- CYP2D6 → Major Depression (drug metabolism)
- COX-2 → Chronic Pain Syndrome, Osteoarthritis, Rheumatoid Arthritis
- TNF-alpha → Rheumatoid Arthritis
- PCSK9 → associated with cardiovascular conditions
- HLA-B → autoimmune conditions
- MTHFR → various conditions"""
    },
    {
        "focus": "gene-pathway membership",
        "instruction": """Generate 12-15 gene-pathway relationships (relationship_type: "part_of_pathway").
Connect every gene to at least 1-2 pathways:
- ACE part of Renin-Angiotensin System
- VKORC1 part of Coagulation Cascade
- CYP2D6 part of Serotonin Pathway (drug metabolism)
- AMPK part of Insulin Signaling Pathway
- COX-2 part of Inflammatory Response Pathway, Pain Signaling Pathway
- TNF-alpha part of Inflammatory Response Pathway
- PCSK9 part of Cholesterol Metabolism Pathway
- SLC22A1 part of Insulin Signaling Pathway (transporter)
- MTHFR part of various pathways"""
    },
    {
        "focus": "drug side effects and contraindications",
        "instruction": """Generate 20-25 relationships mixing:
- "causes_side_effect" (drug → symptom): each drug should cause 2-3 side effects
- "contraindicated" (drug → disease): 5-8 contraindication relationships
Examples:
- Warfarin causes Bleeding, Nausea
- Metformin causes Stomach Pain, Nausea
- Ibuprofen causes Stomach Pain, Dizziness, Swelling
- Prednisone causes Weight Gain, Insomnia, Muscle Weakness
- Sertraline causes Insomnia, Nausea, Dizziness
- Methotrexate contraindicated in pregnancy-related conditions
- NSAIDs contraindicated in Heart Failure"""
    },
]


def main():
    logger.info("Supplementing relationships...")
    client = get_openai_client()

    entities = load_json("entities.json")
    existing_rels = load_json("relationships.json")

    entity_names = sorted(set(e["name"] for e in entities))
    entity_list_str = ", ".join(entity_names)

    # Track existing pairs to avoid duplicates
    existing_pairs = set()
    for r in existing_rels:
        key = (r["source"], r["target"], r["relationship_type"])
        existing_pairs.add(key)

    all_new = []

    for batch in BATCHES:
        logger.info("Generating batch: %s", batch["focus"])
        user_prompt = f"""Available entities: {entity_list_str}

Existing relationship count: {len(existing_rels) + len(all_new)}

{batch['instruction']}

Return the JSON with "relationships" array. Use ONLY entity names from the list above."""

        result = chat_json(client, SYSTEM_PROMPT, user_prompt, temperature=0.7)
        new_rels = result.get("relationships", [])

        # Filter out duplicates and invalid references
        entity_set = set(entity_names)
        valid = []
        for r in new_rels:
            if r["source"] not in entity_set or r["target"] not in entity_set:
                continue
            key = (r["source"], r["target"], r["relationship_type"])
            if key not in existing_pairs:
                valid.append(r)
                existing_pairs.add(key)

        all_new.extend(valid)
        logger.info("  Generated %d, kept %d valid new", len(new_rels), len(valid))

    # Merge with existing
    combined = existing_rels + all_new
    logger.info("Total relationships: %d (was %d, added %d)", len(combined), len(existing_rels), len(all_new))

    from collections import Counter
    dist = Counter(r["relationship_type"] for r in combined)
    for t, c in sorted(dist.items()):
        logger.info("  %s: %d", t, c)

    save_json(combined, "relationships.json")
    logger.info("Done!")


if __name__ == "__main__":
    main()
