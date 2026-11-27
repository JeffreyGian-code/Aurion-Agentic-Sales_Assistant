import hashlib
import json
import math
import os
from uuid import UUID

import httpx

from app.models.recommendation import VehicleEvidence
from app.RAG.ingestion.vehicle_knowledge import EvidenceMatch, KnowledgeEntry
from app.RAG.embeddings.embedding_service import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, OpenRouterEmbeddings


COLLECTIONS_PATH = "/api/v2/tenants/default_tenant/databases/default_database/collections"
INDEX_BATCH_SIZE = 32


class ChromaKnowledgeError(RuntimeError):
    pass


class ChromaVehicleKnowledge:
    """Index public evidence and retrieve similar passages from a complete revision."""

    def __init__(
        self, entries: list[KnowledgeEntry], *, embeddings: OpenRouterEmbeddings | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        port = os.getenv("CHROMA_PORT") or "8001"
        self._url = os.getenv("CHROMA_URL") or f"http://127.0.0.1:{port}"
        self._transport = transport
        self._embeddings = embeddings if embeddings is not None else OpenRouterEmbeddings()
        self._entries = sorted(entries, key=lambda entry: entry.id)
        self._metadata = [
            {
                **entry.model_dump(exclude={"evidence", "facts", "trim_rank"}),
                "variant": entry.variant or "",
                "trim_rank": entry.trim_rank or 0,
                "facts": json.dumps([fact.model_dump() for fact in entry.facts], ensure_ascii=False),
                **entry.evidence.model_dump(),
            }
            for entry in self._entries
        ]
        fingerprint = hashlib.sha256(json.dumps(
            ["vehicle-description-v1", EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, self._metadata],
            sort_keys=True,
        ).encode()).hexdigest()[:32]
        self.collection_name = f"aurion-semantic-{fingerprint}"
        self._active_path: str | None = None

    def build(self) -> int:
        collection = self._request("POST", COLLECTIONS_PATH, {
            "name": self.collection_name,
            "get_or_create": True,
            "configuration": {"hnsw": {"space": "cosine"}},
        })
        path = self._path(collection)
        if not self._complete(path):
            for offset in range(0, len(self._metadata), INDEX_BATCH_SIZE):
                batch = self._metadata[offset:offset + INDEX_BATCH_SIZE]
                passages = [entry.passage for entry in self._entries[offset:offset + INDEX_BATCH_SIZE]]
                vectors = self._embeddings.embed(passages, mode="passage")
                self._request("POST", f"{path}/upsert", {
                    "ids": [f"vehicle:{row['id']}" for row in batch],
                    "documents": passages,
                    "metadatas": batch,
                    "embeddings": vectors,
                })
            if not self._complete(path):
                raise ChromaKnowledgeError("The Chroma evidence index is incomplete.")
        self._active_path = path
        return len(self._entries)

    @property
    def active_path(self) -> str:
        if self._active_path is None:
            collection = self._request("GET", f"{COLLECTIONS_PATH}/{self.collection_name}")
            path = self._path(collection)
            if not self._complete(path):
                raise ChromaKnowledgeError("The Chroma evidence index is incomplete. Run the indexing command.")
            self._active_path = path
        return self._active_path

    def _complete(self, path: str) -> bool:
        return self._request("GET", f"{path}/count") == len(self._entries)

    @staticmethod
    def _path(collection) -> str:
        try:
            return f"{COLLECTIONS_PATH}/{UUID(collection['id'])}"
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ChromaKnowledgeError("Invalid Chroma collection response.") from exc

    def semantic_matches(
        self, preferences: list[str], vehicle_ids: list[int] | None,
    ) -> list[list[EvidenceMatch]]:
        if not preferences or vehicle_ids == []:
            return [[] for _ in preferences]
        path = self.active_path
        query = {
            "query_embeddings": self._embeddings.embed(preferences, mode="query"),
            # Keep every eligible variant available for multi-preference ranking.
            "n_results": len(self._entries),
            "include": ["metadatas", "distances"],
        }
        if vehicle_ids is not None:
            query["where"] = {"id": {"$in": vehicle_ids}}
        result = self._request("POST", f"{path}/query", query)
        try:
            matches = []
            for rows, distances in zip(result["metadatas"], result["distances"], strict=True):
                group = []
                for row, distance in zip(rows, distances, strict=True):
                    if not math.isfinite(distance):
                        raise ValueError("Invalid Chroma distance.")
                    group.append(EvidenceMatch(self._entry(row), 1 - distance))
                matches.append(group)
            if len(matches) != len(preferences):
                raise ValueError("Incomplete Chroma query response.")
            return matches
        except (KeyError, TypeError, ValueError) as exc:
            raise ChromaKnowledgeError("Invalid Chroma query response.") from exc

    def requirement_entries(self, topics: list[str]) -> list[KnowledgeEntry]:
        if not topics:
            return []
        ids = [entry.id for entry in self._entries
               if any(fact.present and fact.topic in topics for fact in entry.facts)]
        return list(self.entries_for_ids(ids).values())

    def entries_for_ids(self, vehicle_ids: list[int]) -> dict[int, KnowledgeEntry]:
        if not vehicle_ids:
            return {}
        result = self._request("POST", f"{self.active_path}/get", {
            "ids": [f"vehicle:{vehicle_id}" for vehicle_id in vehicle_ids],
            "include": ["metadatas"],
        })
        try:
            entries = [self._entry(row) for row in result["metadatas"]]
            return {entry.id: entry for entry in entries}
        except (KeyError, TypeError, ValueError) as exc:
            raise ChromaKnowledgeError("Invalid Chroma evidence response.") from exc

    @staticmethod
    def _entry(row) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=row["id"], brand=row["brand"], model=row["model"],
            variant=row["variant"] or None, vehicle_type=row["vehicle_type"],
            evidence=VehicleEvidence.model_validate(row),
            manufacturer_context=row["manufacturer_context"],
            trim_rank=row["trim_rank"] or None,
            facts=json.loads(row["facts"]),
        )

    def _request(self, method: str, path: str, payload: dict | None = None):
        try:
            with httpx.Client(base_url=self._url, timeout=5, trust_env=False,
                              transport=self._transport) as client:
                return client.request(method, path, json=payload).raise_for_status().json()
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            raise ChromaKnowledgeError("Could not access Chroma evidence. Check that the revision is indexed.") from exc
