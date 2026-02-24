"""
Generate biomedical entity data using Azure OpenAI.

Produces ~60 entities across 5 types: drug, disease, gene, symptom, pathway.
Output: data/entities.json
"""

import logging
import sys

from helpers import get_openai_client, chat_json, save_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kg.generate_entities")

SYSTEM_PROMPT = """\
You are a biomedical knowledge expert. Generate realistic biomedical entities for a knowledge graph demo.
Return a JSON object with a single key "entities" containing an array of entity objects.
Each entity must have:
- "node_type": one of "drug", "disease", "gene", "symptom", "pathway"
- "name": the canonical name (e.g. "Warfarin", "Type 2 Diabetes")
- "description": a 2-3 sentence description of what this entity is, its role in medicine/biology
- "properties": an object with type-specific attributes:
  - For drugs: {"drug_class": "...", "mechanism": "...", "route": "oral|iv|topical|..."}
  - For diseases: {"category": "...", "prevalence": "common|rare|...", "chronic": true|false}
  - For genes: {"chromosome": "...", "function": "...", "associated_drugs": [...]}
  - For symptoms: {"severity": "mild|moderate|severe", "body_system": "..."}
  - For pathways: {"biological_system": "...", "key_molecules": [...]}

IMPORTANT: Generate entities that will create a rich, interconnected graph. Include:
- 15 drugs covering cardiovascular, diabetes, pain, neurological, and autoimmune areas
- 12 diseases spanning these therapeutic areas with varying severity
- 10 genes that are drug targets or disease-associated
- 12 symptoms that overlap across multiple diseases
- 8 biological pathways that connect drugs to their mechanisms

Make the entities medically realistic but simplified for a learning demo.
"""

USER_PROMPT = """\
Generate exactly 57 biomedical entities following the distribution:
- 15 drugs (e.g. Warfarin, Metformin, Lisinopril, Sertraline, Ibuprofen, Aspirin, Methotrexate, Insulin, Atorvastatin, Omeprazole, Clopidogrel, Amoxicillin, Prednisone, Levothyroxine, Gabapentin)
- 12 diseases (e.g. Type 2 Diabetes, Hypertension, Rheumatoid Arthritis, Major Depression, Atrial Fibrillation, Chronic Pain Syndrome, Hypothyroidism, GERD, Heart Failure, Deep Vein Thrombosis, Epilepsy, Osteoarthritis)
- 10 genes (e.g. CYP2D6, VKORC1, ACE, AMPK, COX-2, TNF-alpha, SLC22A1, HLA-B, MTHFR, PCSK9)
- 12 symptoms (e.g. Headache, Fatigue, Nausea, Joint Pain, Dizziness, Bleeding, Muscle Weakness, Insomnia, Shortness of Breath, Swelling, Weight Gain, Stomach Pain)
- 8 pathways (e.g. Renin-Angiotensin System, Coagulation Cascade, Serotonin Pathway, Inflammatory Response Pathway, Insulin Signaling Pathway, Thyroid Hormone Pathway, Cholesterol Metabolism Pathway, Pain Signaling Pathway)

Return the JSON object with the "entities" array.
"""


def main():
    logger.info("Generating biomedical entities...")
    client = get_openai_client()

    result = chat_json(client, SYSTEM_PROMPT, USER_PROMPT, temperature=0.7)
    entities = result.get("entities", [])

    logger.info("Generated %d entities", len(entities))

    # Log type distribution
    from collections import Counter
    dist = Counter(e["node_type"] for e in entities)
    for t, c in sorted(dist.items()):
        logger.info("  %s: %d", t, c)

    save_json(entities, "entities.json")
    logger.info("Done! Saved to data/entities.json")


if __name__ == "__main__":
    main()
