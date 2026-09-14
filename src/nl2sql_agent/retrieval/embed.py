"""Embeddings via l'API Mistral."""

import httpx

from nl2sql_agent.config import get_settings

URL = "https://api.mistral.ai/v1/embeddings"

# L'API accepte une liste ; on découpe pour ne pas dépasser la limite de tokens
# par requête sur des textes longs.
BATCH_SIZE = 32


def embed(texts: list[str], timeout: float = 120.0) -> list[list[float]]:
    """Vecteurs des textes, dans le même ordre.

    Les questions et le catalogue doivent passer par le même modèle : deux
    espaces vectoriels différents ne sont pas comparables.
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
        # L'API peut renvoyer les éléments dans le désordre ; on trie par index.
        vectors.extend(item["embedding"] for item in sorted(data, key=lambda d: d["index"]))

    return vectors


def embed_one(text: str) -> list[float]:
    return embed([text])[0]


def to_pgvector(vector: list[float]) -> str:
    """pgvector accepte la forme textuelle '[0.1,0.2,...]'.

    Évite d'ajouter le paquet pgvector-python pour un seul usage.
    """
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"
