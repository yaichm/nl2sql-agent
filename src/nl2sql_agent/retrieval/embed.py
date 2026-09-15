"""Embeddings via the Mistral API."""

import httpx

from nl2sql_agent.config import get_settings

URL = "https://api.mistral.ai/v1/embeddings"

# The API takes a list; we batch to stay under the per-request token limit
# on long texts.
BATCH_SIZE = 32


def embed(texts: list[str], timeout: float = 120.0) -> list[list[float]]:
    """Vectors for the texts, in the same order.

    Questions and catalog must go through the same model — two different
    vector spaces aren't comparable.
    """
    settings = get_settings()
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY absente du .env")

    headers = {"Authorization": f"Bearer {settings.mistral_api_key}"}
    vectors: list[list[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        response = httpx.post(
            URL,
            headers=headers,
            json={"model": settings.embedding_model_api, "input": batch},
            timeout=timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"embeddings : {response.status_code} {response.text[:300]}")
        data = response.json()["data"]
        # The API may return items out of order; sort by index.
        vectors.extend(item["embedding"] for item in sorted(data, key=lambda d: d["index"]))

    return vectors


def embed_one(text: str) -> list[float]:
    return embed([text])[0]


def to_pgvector(vector: list[float]) -> str:
    """pgvector accepts the textual form '[0.1,0.2,...]'.

    Avoids pulling in pgvector-python for a single call site.
    """
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"
