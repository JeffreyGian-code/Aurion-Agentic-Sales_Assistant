import os
from collections import defaultdict

from app.models.recommendation import RecommendationRequest, RecommendationResult, RecommendedVehicle
from app.RAG.ingestion.vehicle_knowledge import EvidenceMatch, KnowledgeIndex, verified_evidence
from app.repositories.vehicle_repository import VehicleRepository


DEFAULT_MIN_SIMILARITY = 0.2199


class RecommendationService:
    def __init__(
        self, repository: VehicleRepository, knowledge: KnowledgeIndex,
        min_similarity: float | None = None,
    ):
        self.repository = repository
        self.knowledge = knowledge
        self.min_similarity = (
            float(os.getenv("RAG_MIN_SIMILARITY", DEFAULT_MIN_SIMILARITY))
            if min_similarity is None else min_similarity
        )
        if not 0 <= self.min_similarity <= 1:
            raise ValueError("RAG_MIN_SIMILARITY must be between zero and one.")

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        filters = request.filters
        required = set(request.required_topics)
        combined = filters is not None and bool(filters.model_dump(exclude_none=True, exclude={"sort_order"}))
        vehicles = self.repository.search_candidates(filters) if combined else []
        if combined and not vehicles:
            return RecommendationResult(status="no_catalogue_matches")

        requirements = defaultdict(list)
        for entry in self.knowledge.requirement_entries(request.required_topics):
            requirements[entry.id].append(entry)
        if required and not combined:
            vehicles = self.repository.get_by_ids(sorted(requirements))

        verified_requirements = {}
        if required:
            for vehicle in vehicles:
                evidence = verified_evidence(vehicle, requirements[vehicle.id])
                confirmed = {topic: item for topic, item in evidence.items() if item.strength == "confirmed"}
                if required <= confirmed.keys():
                    verified_requirements[vehicle.id] = confirmed
            vehicles = [vehicle for vehicle in vehicles if vehicle.id in verified_requirements]
            if not vehicles:
                return RecommendationResult(status="requirements_unverified")

        eligible_ids = [vehicle.id for vehicle in vehicles] if combined or required else None
        matches = self.knowledge.semantic_matches(request.preferences, eligible_ids)
        relevant = [
            [hit for hit in group if hit.similarity >= self.min_similarity]
            for group in matches
        ]
        if eligible_ids is None:
            ids = sorted({hit.entry.id for group in relevant for hit in group})
            vehicles = self.repository.get_by_ids(ids) if ids else []

        vehicles_by_id = {vehicle.id: vehicle for vehicle in vehicles}
        per_priority: list[dict[int, EvidenceMatch]] = []
        for group in relevant:
            best_by_id = {}
            for hit in group:
                vehicle = vehicles_by_id.get(hit.entry.id)
                if vehicle is None or not verified_evidence(vehicle, [hit.entry]):
                    continue
                current = best_by_id.get(vehicle.id)
                if current is None or (-hit.similarity, hit.entry.evidence.topic) < (
                    -current.similarity, current.entry.evidence.topic
                ):
                    best_by_id[vehicle.id] = hit
            per_priority.append(best_by_id)

        descending = filters is not None and filters.sort_order == "price_desc"
        has_budget = filters is not None and (filters.max_price is not None or filters.min_price is not None)
        ranked = []
        for vehicle in vehicles_by_id.values():
            hits = [group.get(vehicle.id) for group in per_priority]
            if request.preferences and not any(hits):
                continue
            reasons = dict(verified_requirements.get(vehicle.id, {}))
            for hit in hits:
                if hit is not None:
                    reasons[hit.entry.evidence.topic] = hit.entry.evidence
            priority_key = tuple(-hit.similarity if hit is not None else 1 for hit in hits)
            price = -vehicle.price if descending else vehicle.price
            ranked.append((priority_key, price, vehicle.id, RecommendedVehicle(
                vehicle=vehicle,
                evidence=list(reasons.values()),
                matched_preferences=[phrase for phrase, hit in zip(request.preferences, hits) if hit is not None],
                match=("budget_match" if has_budget else "candidate") if request.preferences else "confirmed_match",
            )))

        ranked.sort(key=lambda item: item[:3])
        if not ranked:
            return RecommendationResult(status="clarification_needed")
        return RecommendationResult(status="matches", recommendations=[item[3] for item in ranked[:3]])
