import hashlib
import json
import os
from collections import defaultdict
from uuid import UUID

import httpx

from app.models.recommendation import VehicleEvidence
from app.repositories.vehicle_knowledge import KnowledgeEntry


COLLECTIONS_PATH = "/api/v2/tenants/default_tenant/databases/default_database/collections"
UPSERT_BATCH_SIZE = 500


class ChromaKnowledgeError(RuntimeError):
    pass


class ChromaVehicleKnowledge:
    """Store validated Markdown evidence in Chroma and retrieve it by metadata."""

    def __init__(self, entries: list[KnowledgeEntry], *, transport: httpx.BaseTransport | None = None):
        port = os.getenv("CHROMA_PORT") or "8001"
        self._url = os.getenv("CHROMA_URL") or f"http://127.0.0.1:{port}"
        self._transport = transport
        entries = sorted(entries, key=lambda entry: (entry.id, entry.evidence.topic))
        metadata = [
            {
                **entry.model_dump(exclude={"evidence"}),
                "variant": entry.variant or "",
                **entry.evidence.model_dump(),
            }
            for entry in entries
        ]
        # Separate revisions let concurrent app versions use their own evidence safely.
        fingerprint = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:32]
        collection = self._post(COLLECTIONS_PATH, {
            "name": f"aurion-evidence-{fingerprint}",
            "get_or_create": True,
        })
        try:
            self._collection_path = f"{COLLECTIONS_PATH}/{UUID(collection['id'])}"
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ChromaKnowledgeError("Invalid Chroma collection response.") from exc
        for offset in range(0, len(metadata), UPSERT_BATCH_SIZE):
            batch = metadata[offset:offset + UPSERT_BATCH_SIZE]
            self._post(f"{self._collection_path}/upsert", {
                "ids": [f"{row['id']}:{row['topic']}" for row in batch],
                "metadatas": batch,
                # Chroma requires vectors on upsert. Exact-topic retrieval uses metadata.
                "embeddings": [[1.0]] * len(batch),
            })

    def retrieve(self, topics: list[str]) -> dict[int, list[KnowledgeEntry]]:
        return self._get("topic", topics)

    def entries_for_ids(self, vehicle_ids: list[int]) -> dict[int, list[KnowledgeEntry]]:
        return self._get("id", vehicle_ids)

    def _get(self, field: str, values: list[str] | list[int]) -> dict[int, list[KnowledgeEntry]]:
        if not values:
            return {}
        result = self._post(f"{self._collection_path}/get", {
            "where": {field: {"$in": values}},
            "include": ["metadatas"],
        })
        entries = defaultdict(list)
        try:
            for row in result["metadatas"]:
                entry = KnowledgeEntry(
                    id=row["id"], brand=row["brand"], model=row["model"],
                    variant=row["variant"] or None, vehicle_type=row["vehicle_type"],
                    evidence=VehicleEvidence.model_validate(row),
                )
                entries[entry.id].append(entry)
        except (KeyError, TypeError, ValueError) as exc:
            raise ChromaKnowledgeError("Invalid Chroma evidence response.") from exc
        return dict(entries)

    def _post(self, path: str, payload: dict) -> dict:
        try:
            with httpx.Client(base_url=self._url, timeout=5, trust_env=False,
                              transport=self._transport) as client:
                response = client.post(path, json=payload)
                return response.raise_for_status().json()
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            raise ChromaKnowledgeError("Could not access Chroma evidence.") from exc
