from collections import defaultdict
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from app.models.recommendation import VehicleEvidence
from app.models.vehicle import Vehicle


KNOWLEDGE_PATH = Path(__file__).resolve().parents[2] / "data" / "vehicle_knowledge.md"
TABLE_HEADER = "| ID | Brand | Model | Variant | Body type | Topic | Strength | Reason | Source |"


class KnowledgeEntry(BaseModel):
    id: int = Field(gt=0, le=2147483647)
    brand: str = Field(min_length=1)
    model: str = Field(min_length=1)
    variant: str | None
    vehicle_type: str = Field(min_length=1)
    evidence: VehicleEvidence

    @property
    def identity(self):
        return (self.brand.casefold(), self.model.casefold(),
                (self.variant or "").casefold(), self.vehicle_type.casefold())


class KnowledgeIndex(Protocol):
    def retrieve(self, topics: list[str]) -> dict[int, list[KnowledgeEntry]]: ...

    def entries_for_ids(self, vehicle_ids: list[int]) -> dict[int, list[KnowledgeEntry]]: ...


def verified_evidence(vehicle: Vehicle, entries: list[KnowledgeEntry]) -> dict[str, VehicleEvidence]:
    identity = (vehicle.brand.casefold(), vehicle.model.casefold(),
                (vehicle.variant or "").casefold(), vehicle.vehicle_type.casefold())
    return {
        entry.evidence.topic: entry.evidence for entry in entries
        if entry.id == vehicle.id and entry.identity == identity
    }


class VehicleKnowledge:
    """Index the local Markdown evidence by topic and by catalogue variant ID."""

    def __init__(self, path: Path = KNOWLEDGE_PATH):
        self._entries: dict[int, list[KnowledgeEntry]] = defaultdict(list)
        self._ids_by_topic: dict[str, set[int]] = defaultdict(set)
        ids_by_identity = {}
        in_table = False
        for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if line == TABLE_HEADER:
                in_table = True
                continue
            if not line.startswith("|"):
                in_table = False
                continue
            if not in_table:
                raise ValueError(f"{path}:{number}: unexpected knowledge table")
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 9 and all(cell == "---" for cell in cells):
                continue
            try:
                vehicle_id, brand, model, variant, body_type, topic, strength, reason, source = cells
                entry = KnowledgeEntry(
                    id=vehicle_id, brand=brand, model=model, variant=variant or None,
                    vehicle_type=body_type,
                    evidence=VehicleEvidence(topic=topic, strength=strength, reason=reason, source=source),
                )
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: invalid vehicle evidence row") from exc
            existing = self._entries[entry.id]
            variant_key = entry.identity[:3]
            if (
                (existing and existing[0].identity != entry.identity)
                or ids_by_identity.get(variant_key, entry.id) != entry.id
                or entry.id in self._ids_by_topic[topic]
            ):
                raise ValueError(f"{path}:{number}: conflicting vehicle ID or duplicate topic")
            ids_by_identity[variant_key] = entry.id
            existing.append(entry)
            self._ids_by_topic[topic].add(entry.id)
        if not self._entries:
            raise ValueError(f"{path}: missing vehicle evidence")

    def retrieve(self, topics: list[str]) -> dict[int, list[KnowledgeEntry]]:
        ids = {vehicle_id for topic in topics for vehicle_id in self._ids_by_topic.get(topic, ())}
        return {vehicle_id: self._entries[vehicle_id] for vehicle_id in sorted(ids)}

    def entries_for_ids(self, vehicle_ids: list[int]) -> dict[int, list[KnowledgeEntry]]:
        return {vehicle_id: self._entries[vehicle_id] for vehicle_id in vehicle_ids if vehicle_id in self._entries}

    def all_entries(self) -> list[KnowledgeEntry]:
        return [entry for entries in self._entries.values() for entry in entries]
