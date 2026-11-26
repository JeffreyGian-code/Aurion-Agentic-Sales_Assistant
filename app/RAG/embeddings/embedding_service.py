import math
import os

import httpx


EMBEDDING_MODEL = "nvidia/nemotron-3.5-embed-1b:free"
EMBEDDING_DIMENSIONS = 2048
EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"


class EmbeddingError(RuntimeError):
    pass


class OpenRouterEmbeddings:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def embed(self, texts: list[str], *, mode: str) -> list[list[float]]:
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise EmbeddingError("OpenRouter embedding credentials are unavailable.")
        try:
            with httpx.Client(timeout=12, transport=self._transport) as client:
                response = client.post(
                    EMBEDDING_URL, headers={"Authorization": f"Bearer {key}"},
                    json={"model": EMBEDDING_MODEL, "input": texts, "input_type": mode,
                          "encoding_format": "float"},
                )
                response.raise_for_status()
                rows = sorted(response.json()["data"], key=lambda row: row["index"])
            vectors = [row["embedding"] for row in rows]
            if [row["index"] for row in rows] != list(range(len(texts))) or any(
                len(vector) != EMBEDDING_DIMENSIONS
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector)
                or not any(vector)
                for vector in vectors
            ):
                raise ValueError("Invalid embedding vectors.")
            return vectors
        except (httpx.HTTPError, KeyError, ValueError, TypeError, OverflowError) as exc:
            raise EmbeddingError("OpenRouter embeddings are temporarily unavailable.") from exc
