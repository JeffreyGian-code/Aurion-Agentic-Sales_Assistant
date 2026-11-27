"""Opt-in quality check for the live vehicle description index."""

from dotenv import load_dotenv

from app.models.recommendation import RecommendationRequest
from app.models.SearchRequest import SearchRequest
from app.tools.agent_tools import AgentTools


CASES = [
    ("upright driving position with room for weekend bags", "Elevate", None),
    ("family SUV with reclining rear seats for school runs", "Creta", None),
    ("strong hybrid for daily drives and longer journeys", "Urban Cruiser Hyryder", None),
    ("small hatchback for errands and loading groceries", "Tiago", 800000),
    ("weekend outings with a choice of roof and four-wheel drive", "Thar", None),
]


def main():
    load_dotenv()
    tools = AgentTools()
    passed = 0
    for preference, expected, budget in CASES:
        result = tools.recommend_vehicles(RecommendationRequest(
            preferences=[preference],
            filters=SearchRequest(max_price=budget) if budget is not None else None,
        ))
        models = [entry["vehicle"]["model"] for entry in result["recommendations"]]
        passed += expected in models
        print(f"{preference} | expected {expected} | {result['status']}: {', '.join(models)}")
    print(f"Expected model in shortlist for {passed}/{len(CASES)} queries.")


if __name__ == "__main__":
    main()
