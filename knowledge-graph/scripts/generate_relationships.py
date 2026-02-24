"""
Generate relationships between biomedical entities using Azure OpenAI.

Phase 1: Initial generation — LLM produces ~100-150 relationships in one call.
Phase 2: Enrichment batches — targeted batches fill gaps and increase density.

Reads: data/entities.json
Output: data/relationships.json
"""

import logging
from collections import Counter

from helpers import get_openai_client, chat_json, save_json, load_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kg.generate_relationships")

PHASE1_SYSTEM = """\
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
2. Include drug-drug interactions (interacts_with) — crucial for graph search demo
3. Create overlapping symptom-disease links (same symptom for multiple diseases)
4. Link multiple drugs to the same pathways and genes to create shared connections
5. Include some contraindications
6. Make the graph rich enough that traversal reveals non-obvious connections
7. Aim for 150-200 relationships total
"""

ENRICHMENT_SYSTEM = """\
You are a biomedical knowledge expert. Generate additional realistic relationships between biomedical entities.
Return a JSON object with key "relationships" containing an array.
Each must have: "source", "target", "relationship_type", "properties" (with "strength", "evidence", "description").
Only use entity names from the provided list. Do NOT duplicate any existing relationship.
"""

# ── Phase 2: targeted enrichment batches ──
ENRICHMENT_BATCHES = [
    # --- Drug-drug interactions ---
    {
        "focus": "drug-drug interactions",
        "instruction": """Generate 15-20 drug-drug interaction relationships (relationship_type: "interacts_with").
Focus on clinically significant interactions like:
- Warfarin interacting with Aspirin, Ibuprofen, Amoxicillin, Omeprazole, Clopidogrel
- Metformin interacting with Prednisone, Lisinopril
- Sertraline interacting with Ibuprofen, Aspirin, Gabapentin
- Atorvastatin interacting with Omeprazole, Amoxicillin
- Prednisone interacting with Aspirin, Ibuprofen, Methotrexate, Insulin
- Levothyroxine interacting with Warfarin, Omeprazole, Metformin, Sertraline
- Gabapentin interacting with Prednisone, Ibuprofen, Sertraline
- Insulin interacting with Metformin, Prednisone, Aspirin, Lisinopril
- Clopidogrel interacting with Omeprazole, Ibuprofen, Prednisone
- Methotrexate interacting with Ibuprofen, Aspirin, Omeprazole, Amoxicillin
All interactions should be clinically plausible."""
    },
    # --- Disease-symptom connections ---
    {
        "focus": "disease-symptom connections",
        "instruction": """Generate 20-25 disease-symptom relationships (relationship_type: "presents_as").
Make symptoms overlap across diseases:
- Fatigue should be linked to at least 5 diseases
- Headache to at least 3 diseases
- Nausea to at least 4 diseases
- Joint Pain to at least 3 diseases
- Shortness of Breath and Swelling to cardiovascular diseases
- Weight Gain to metabolic/endocrine diseases
- Atrial Fibrillation presents as Shortness of Breath, Dizziness, Fatigue
- Heart Failure presents as Shortness of Breath, Swelling, Fatigue, Weight Gain
- Epilepsy presents as Dizziness, Headache, Muscle Weakness
- GERD presents as Stomach Pain, Nausea
- Deep Vein Thrombosis presents as Swelling, Shortness of Breath
- Hypothyroidism presents as Fatigue, Weight Gain, Muscle Weakness
- Chronic Pain Syndrome presents as Insomnia, Fatigue"""
    },
    # --- Gene-disease associations ---
    {
        "focus": "gene-disease associations",
        "instruction": """Generate 15-20 disease-gene associations (relationship_type: "associated_with").
Link genes to diseases they're known to be involved in:
- ACE → Hypertension, Heart Failure
- VKORC1 → Deep Vein Thrombosis, Atrial Fibrillation
- AMPK → Type 2 Diabetes
- CYP2D6 → Major Depression (drug metabolism), Epilepsy
- COX-2 → Chronic Pain Syndrome, Osteoarthritis, Rheumatoid Arthritis
- TNF-alpha → Rheumatoid Arthritis
- PCSK9 → associated with cardiovascular conditions, Heart Failure
- HLA-B → autoimmune conditions
- MTHFR → various conditions, Major Depression
- Osteoarthritis associated_with COX-2"""
    },
    # --- Gene-pathway membership ---
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
    # --- Drug side effects and contraindications ---
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
- NSAIDs (Ibuprofen, Aspirin) contraindicated in Heart Failure, GERD
- Metformin contraindicated in Heart Failure (sometimes)
- Methotrexate contraindicated in Hypothyroidism"""
    },
    # --- Drug-pathway and drug-gene connections ---
    {
        "focus": "drug-pathway and drug-gene connections",
        "instruction": """Generate 20-25 relationships mixing:
- "involves_pathway" (drug → pathway): connect drugs to pathways they act through
- "targets_gene" (drug → gene): connect drugs to gene targets

Every drug should act through at least 1 pathway. Key connections:
- Aspirin involves Inflammatory Response Pathway, Coagulation Cascade, Pain Signaling Pathway
- Sertraline involves Serotonin Pathway, targets CYP2D6
- Atorvastatin involves Cholesterol Metabolism Pathway, targets PCSK9
- Methotrexate targets MTHFR, involves Inflammatory Response Pathway
- Gabapentin involves Pain Signaling Pathway
- Levothyroxine involves Thyroid Hormone Pathway
- Insulin involves Insulin Signaling Pathway, targets AMPK
- Prednisone involves Inflammatory Response Pathway, targets TNF-alpha
- Omeprazole targets CYP2D6 (inhibits it)
- Amoxicillin targets HLA-B (hypersensitivity)
- Clopidogrel involves Coagulation Cascade, targets CYP2D6"""
    },
    # --- Drug treats and additional contraindications ---
    {
        "focus": "drug treats and contraindications",
        "instruction": """Generate 15-20 relationships mixing:
- "treats" (drug → disease): drugs treating conditions
- "contraindicated" (drug → disease): drugs that should NOT be used

Key connections:
- Aspirin treats Chronic Pain Syndrome, Atrial Fibrillation (off-label)
- Gabapentin treats Epilepsy, Chronic Pain Syndrome
- Sertraline treats Major Depression
- Levothyroxine treats Hypothyroidism
- Atorvastatin treats (prevents) Heart Failure
- Prednisone treats Rheumatoid Arthritis, Osteoarthritis
- Clopidogrel treats Deep Vein Thrombosis, Atrial Fibrillation
- Ibuprofen contraindicated in Heart Failure, GERD
- Aspirin contraindicated in Bleeding disorders"""
    },
]


def _log_distribution(rels: list[dict]) -> None:
    dist = Counter(r["relationship_type"] for r in rels)
    for t, c in sorted(dist.items()):
        logger.info("  %s: %d", t, c)


def _validate(rels: list[dict], entity_names: set[str]) -> list[dict]:
    """Keep only relationships referencing valid entities."""
    valid = []
    invalid_count = 0
    for r in rels:
        if r["source"] in entity_names and r["target"] in entity_names:
            valid.append(r)
        else:
            invalid_count += 1
    if invalid_count:
        logger.warning("Dropped %d relationships with unknown entities", invalid_count)
    return valid


def _dedup_merge(existing: list[dict], new_rels: list[dict]) -> list[dict]:
    """Merge new relationships, skipping duplicates."""
    seen = {(r["source"], r["target"], r["relationship_type"]) for r in existing}
    added = 0
    for r in new_rels:
        key = (r["source"], r["target"], r["relationship_type"])
        if key not in seen:
            existing.append(r)
            seen.add(key)
            added += 1
    logger.info("  Kept %d new (skipped %d duplicates)", added, len(new_rels) - added)
    return existing


def main():
    client = get_openai_client()
    entities = load_json("entities.json")
    entity_names = {e["name"] for e in entities}
    entity_list = "\n".join(f"- [{e['node_type']}] {e['name']}" for e in entities)
    entity_list_str = ", ".join(sorted(entity_names))

    # ── Phase 1: initial generation ──
    logger.info("Phase 1: Generating initial relationships...")
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
    result = chat_json(client, PHASE1_SYSTEM, user_prompt, temperature=0.7)
    relationships = _validate(result.get("relationships", []), entity_names)
    logger.info("Phase 1 generated %d relationships", len(relationships))
    _log_distribution(relationships)

    # ── Phase 2: targeted enrichment batches ──
    logger.info("Phase 2: Enrichment batches (%d batches)...", len(ENRICHMENT_BATCHES))
    for batch in ENRICHMENT_BATCHES:
        logger.info("Batch: %s", batch["focus"])
        user_prompt = f"""Available entities: {entity_list_str}

Existing relationship count: {len(relationships)}

{batch['instruction']}

Return the JSON with "relationships" array. Use ONLY entity names from the list above.
Do NOT duplicate existing relationships."""

        result = chat_json(client, ENRICHMENT_SYSTEM, user_prompt, temperature=0.6)
        new_rels = _validate(result.get("relationships", []), entity_names)
        relationships = _dedup_merge(relationships, new_rels)

    logger.info("Final total: %d relationships", len(relationships))
    _log_distribution(relationships)

    save_json(relationships, "relationships.json")
    logger.info("Done! Saved to data/relationships.json")


if __name__ == "__main__":
    main()
