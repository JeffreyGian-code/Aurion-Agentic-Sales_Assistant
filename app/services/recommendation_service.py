from app.models.recommendation import RecommendationRequest, RecommendedVehicle
from app.repositories.vehicle_knowledge import KnowledgeIndex, verified_evidence
from app.repositories.vehicle_repository import VehicleRepository


class RecommendationService:
    def __init__(self, repository: VehicleRepository, knowledge: KnowledgeIndex):
        self.repository = repository
        self.knowledge = knowledge

    def recommend(self, request: RecommendationRequest) -> list[RecommendedVehicle]:
        topics = [priority.topic for priority in request.priorities]
        retrieved = self.knowledge.retrieve(topics)
        filters = request.filters
        combined = filters is not None and bool(filters.model_dump(exclude_none=True, exclude={"sort_order"}))
        if combined:
            vehicles = self.repository.search_candidates(filters)
        else:
            vehicles = self.repository.get_by_ids(list(retrieved))

        vehicles_by_id = {vehicle.id: vehicle for vehicle in vehicles}
        missed_ids = [vehicle_id for vehicle_id in vehicles_by_id if vehicle_id not in retrieved]
        if missed_ids:
            retrieved.update(self.knowledge.entries_for_ids(missed_ids))

        descending = filters is not None and filters.sort_order == "price_desc"
        has_budget = filters is not None and (filters.max_price is not None or filters.min_price is not None)
        ranked = []
        for vehicle in vehicles_by_id.values():
            evidence = verified_evidence(vehicle, retrieved.get(vehicle.id, []))
            confirmed = {topic for topic, item in evidence.items() if item.strength == "confirmed"}
            if any(priority.required and priority.topic not in confirmed for priority in request.priorities):
                continue

            reasons = [evidence[topic] for topic in topics if topic in evidence]
            if not reasons and not combined:
                continue
            if all(topic in confirmed for topic in topics):
                match = "confirmed_match"
            elif has_budget:
                match = "budget_match"
            elif reasons:
                match = "candidate"
            else:
                match = "filter_match"

            # Compare priorities in buyer order, then use listed price and ID for ties.
            priority_key = tuple(-2 if topic in confirmed else -int(topic in evidence) for topic in topics)
            price = -vehicle.price if descending else vehicle.price
            ranked.append((priority_key, price, vehicle.id, RecommendedVehicle(
                vehicle=vehicle, evidence=reasons, match=match,
            )))

        ranked.sort(key=lambda item: item[:3])
        return [item[3] for item in ranked[:3]]
