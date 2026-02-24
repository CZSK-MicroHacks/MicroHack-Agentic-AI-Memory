"""
Shared helpers for knowledge-graph scripts: Azure OpenAI client, embedding, data I/O.
"""

from __future__ import annotations

import json
import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()
logger = logging.getLogger("kg.helpers")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def get_openai_client() -> AzureOpenAI:
    """Return a synchronous Azure OpenAI client."""
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    # Try API key first, fall back to DefaultAzureCredential
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if api_key:
        return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)

    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    return AzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=token_provider, api_version=api_version)


def chat_json(client: AzureOpenAI, system: str, user: str, *, temperature: float = 0.7) -> dict | list:
    """Send a chat request expecting JSON output and parse the response."""
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content
    return json.loads(text)


def compute_embeddings(client: AzureOpenAI, texts: list[str], *, batch_size: int = 16) -> list[list[float]]:
    """Compute embeddings in batches, returning 1536-dim vectors."""
    deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large")
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(
            model=deployment,
            input=batch,
            dimensions=1536,
        )
        for item in resp.data:
            all_embeddings.append(item.embedding)
        logger.info("Embedded batch %d-%d / %d", i, i + len(batch), len(texts))

    return all_embeddings


def save_json(data: any, filename: str) -> Path:
    """Save data to DATA_DIR/<filename>."""
    path = DATA_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Saved %s (%d bytes)", path, path.stat().st_size)
    return path


def load_json(filename: str) -> any:
    """Load data from DATA_DIR/<filename>."""
    path = DATA_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
