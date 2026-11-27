import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from app.models.recommendation import Topic, VehicleEvidence
from app.models.vehicle import Vehicle


KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "documents" / "vehicle_knowledge.md"
VARIANT_LINE = re.compile(r"^- \*\*ID (\d+) — (.+?)\*\* · ([^·]+)(.*)$")
FACT_LINE = re.compile(r"^- \*\*ID (\d+) · ([a-z][a-z0-9_]{0,59}) · (present|absent)\*\*\. (.+) \[Source\]\((https?://\S+)\)$")


class TrimFact(BaseModel):
    topic: Topic
    present: bool
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)


class KnowledgeEntry(BaseModel):
    id: int = Field(gt=0, le=2147483647)
    brand: str = Field(min_length=1)
    model: str = Field(min_length=1)
    variant: str | None
    vehicle_type: str = Field(min_length=1)
    evidence: VehicleEvidence
    manufacturer_context: str = ""
    trim_rank: int | None = Field(default=None, ge=1)
    facts: list[TrimFact] = Field(default_factory=list)

    @property
    def passage(self) -> str:
        return " ".join([self.evidence.reason, *(fact.reason for fact in self.facts if fact.present)])

    def matches_vehicle(self, vehicle: Vehicle) -> bool:
        return self.id == vehicle.id and identity(self) == identity(vehicle)


def identity(vehicle: KnowledgeEntry | Vehicle) -> tuple[str, str, str, str]:
    return (vehicle.brand.casefold(), vehicle.model.casefold(),
            (vehicle.variant or "").casefold(), vehicle.vehicle_type.casefold())


class KnowledgeIndex(Protocol):
    def semantic_matches(
        self, preferences: list[str], vehicle_ids: list[int] | None,
    ) -> list[list["EvidenceMatch"]]: ...
    def requirement_entries(self, topics: list[str]) -> list[KnowledgeEntry]: ...
    def entries_for_ids(self, vehicle_ids: list[int]) -> dict[int, KnowledgeEntry]: ...


@dataclass(frozen=True)
class EvidenceMatch:
    entry: KnowledgeEntry
    similarity: float


def verified_evidence(vehicle: Vehicle, entries: list[KnowledgeEntry]) -> dict[str, VehicleEvidence]:
    return {
        fact.topic: VehicleEvidence(
            topic=fact.topic, strength="confirmed", reason=fact.reason, source=fact.source,
        )
        for entry in entries if entry.matches_vehicle(vehicle)
        for fact in entry.facts if fact.present
    }


class VehicleKnowledge:
    """Read model descriptions and catalogue variant lists from Markdown."""

    def __init__(self, path: Path = KNOWLEDGE_PATH):
        self._entries: dict[int, KnowledgeEntry] = {}
        identities = set()
        source = f"app/RAG/documents/{path.name}"
        sections = re.split(r"^## (.+)$", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        for name, body in zip(sections[1::2], sections[2::2], strict=True):
            blocks = re.split(r"^### (.+)$", body, flags=re.MULTILINE)
            parts = dict(zip(blocks[1::2], blocks[2::2], strict=True))
            if "Seeded catalogue variants" not in parts:
                continue
            name = name.strip()
            description = " ".join(blocks[0].split())
            if not description:
                raise ValueError(f"{path}: missing description for {name}")
            facts = {}
            for line in parts.get("Verified catalogue equipment", "").splitlines():
                if not line.strip():
                    continue
                match = FACT_LINE.fullmatch(line.strip())
                if not match:
                    raise ValueError(f"{path}: invalid verified equipment row for {name}")
                vehicle_id, topic, status, reason, citation = match.groups()
                vehicle_facts = facts.setdefault(int(vehicle_id), {})
                if topic in vehicle_facts:
                    raise ValueError(f"{path}: duplicate equipment topic for vehicle {vehicle_id}")
                vehicle_facts[topic] = TrimFact(
                    topic=topic, present=status == "present", reason=reason, source=citation,
                )

            for line in parts["Seeded catalogue variants"].splitlines():
                if not line.strip():
                    continue
                match = VARIANT_LINE.fullmatch(line.strip())
                if not match:
                    raise ValueError(f"{path}: invalid catalogue variant row for {name}")
                vehicle_id, label, body_type, notes = match.groups()
                if label != name and not label.startswith(f"{name} "):
                    raise ValueError(f"{path}: variant {label} is outside the {name} section")
                vehicle_id = int(vehicle_id)
                rank = re.search(r"· Trim rank (\d+)(?:\s*·|$)", notes)
                brand, model = name.split(" ", 1)
                if name.startswith("Maruti Suzuki "):
                    brand, model = "Maruti Suzuki", name.removeprefix("Maruti Suzuki ")
                entry = KnowledgeEntry(
                    id=vehicle_id, brand=brand, model=model, variant=label[len(name):].strip() or None,
                    vehicle_type=body_type.strip(),
                    evidence=VehicleEvidence(
                        topic="vehicle_description", strength="indicative",
                        reason=f"{label} is a {body_type.strip().lower()}. {description}",
                        source=f"{source}#{re.sub(r'[^a-z0-9 -]', '', name.lower()).replace(' ', '-')}",
                    ),
                    manufacturer_context=parts.get("Manufacturer trim comparison", "").strip(),
                    trim_rank=int(rank[1]) if rank else None, facts=list(facts.pop(vehicle_id, {}).values()),
                )
                variant_identity = identity(entry)[:3]
                if vehicle_id in self._entries or variant_identity in identities:
                    raise ValueError(f"{path}: conflicting vehicle ID or variant identity for {vehicle_id}")
                self._entries[vehicle_id] = entry
                identities.add(variant_identity)
            if facts:
                raise ValueError(f"{path}: verified equipment references IDs outside {name}: {sorted(facts)}")
        if not self._entries:
            raise ValueError(f"{path}: missing catalogue variants")

    def all_entries(self) -> list[KnowledgeEntry]:
        return list(self._entries.values())
