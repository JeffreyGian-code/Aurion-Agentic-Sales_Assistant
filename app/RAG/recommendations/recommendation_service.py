import os
from collections import defaultdict

from app.models.recommendation import RecommendationRequest, RecommendationResult, RecommendedVehicle
from app.models.SearchRequest import SearchRequest
from app.RAG.ingestion.vehicle_knowledge import KnowledgeIndex, verified_evidence
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
        per_priority = [
            {hit.entry.id: hit for hit in group
             if hit.entry.id in vehicles_by_id and hit.entry.matches_vehicle(vehicles_by_id[hit.entry.id])}
            for group in relevant
        ]

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
                    reasons.update(verified_evidence(vehicle, [hit.entry]))
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

        shortlist = []
        seen_models = set()
        for _, _, _, recommendation in ranked:
            vehicle = recommendation.vehicle
            model = (vehicle.brand.casefold(), vehicle.model.casefold())
            if (filters is None or filters.model is None) and model in seen_models:
                continue
            shortlist.append(recommendation)
            seen_models.add(model)
            if len(shortlist) == 3:
                break
        return RecommendationResult(status="matches", recommendations=shortlist)

    def describe_vehicle(self, vehicle_id: int) -> dict:
        vehicle = self.repository.get_by_id(vehicle_id)
        if vehicle is None:
            return {"status": "vehicle_not_found"}
        entry = self.knowledge.entries_for_ids([vehicle.id]).get(vehicle.id)
        if entry is None or not entry.matches_vehicle(vehicle):
            return {"status": "description_unavailable", "vehicle": vehicle.model_dump()}
        return {
            "status": "description",
            "vehicle": vehicle.model_dump(),
            "description": entry.evidence.model_dump(),
            "verified_features": [fact.model_dump() for fact in entry.facts],
            "manufacturer_context": entry.manufacturer_context,
        }

    def compare_higher_trims(self, vehicle_id: int, feature: str | None, max_price: int | None) -> dict:
        base = self.repository.get_by_id(vehicle_id)
        if base is None:
            return {"status": "vehicle_not_found"}
        candidates = self.repository.search_candidates(SearchRequest(
            brand=base.brand, model=base.model, min_price=base.price + 1, max_price=max_price,
        )) if max_price is None or max_price > base.price else []
        entries = self.knowledge.entries_for_ids([base.id, *(vehicle.id for vehicle in candidates)])
        base_entry = entries.get(base.id)
        result = {"status": "upgrade_unverified", "vehicle": base.model_dump(), "upgrades": []}
        if base_entry is None or not base_entry.matches_vehicle(base):
            return result
        result["manufacturer_context"] = base_entry.manufacturer_context
        if not candidates:
            result["status"] = "no_higher_priced_trims"
            return result
        if base_entry.trim_rank is None:
            return result

        absent = {fact.topic: fact for fact in base_entry.facts
                  if not fact.present and (feature is None or fact.topic == feature)}
        for vehicle in candidates:
            entry = entries.get(vehicle.id)
            if (entry is None or not entry.matches_vehicle(vehicle)
                    or entry.trim_rank is None or entry.trim_rank <= base_entry.trim_rank):
                continue
            added = [{"feature": fact.model_dump(), "base_evidence": absent[fact.topic].model_dump()}
                     for fact in entry.facts if fact.present and fact.topic in absent]
            if added:
                result["upgrades"].append({
                    "vehicle": vehicle.model_dump(), "price_difference": vehicle.price - base.price, "added": added,
                })
        if result["upgrades"]:
            result["status"] = "verified_upgrades"
            result["upgrades"] = result["upgrades"][:3]
        return result
