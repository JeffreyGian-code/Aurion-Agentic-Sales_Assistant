import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_agent
from app.api.main import app
from app.api.rate_limit import limiter
from app.models.SearchRequest import SearchRequest
from app.repositories import postgres_vehicle_repository
from app.repositories.vehicle_knowledge import EvidenceMatch, TABLE_HEADER, VehicleKnowledge, verified_evidence
from app.services.recommendation_service import RecommendationService
from app.tools.agent_tools import AgentTools


class FixtureIndex:
    def __init__(self, markdown):
        self.markdown = markdown

    def semantic_matches(self, preferences, vehicle_ids):
        topics = {
            "easy in narrow city streets": "commuting",
            "smooth automatic driving": "automatic",
            "close parking": "parking",
        }
        return [
            [
                EvidenceMatch(entry, 0.9 if entry.evidence.topic == topics.get(phrase) else 0.1)
                for entry in self.markdown.all_entries()
                if vehicle_ids is None or entry.id in vehicle_ids
            ]
            for phrase in preferences
        ]

    def requirement_entries(self, topics):
        return [entry for entry in self.markdown.all_entries()
                if entry.evidence.topic in topics and entry.evidence.strength == "confirmed"]


@pytest.fixture
def tools(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE vehicles (
                id INTEGER PRIMARY KEY, brand TEXT, model TEXT, variant TEXT,
                price INTEGER, vehicle_type TEXT
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO vehicles VALUES
                (1, 'Brand', 'One', 'Base', 100, 'Hatchback'),
                (2, 'Brand', 'Two', 'Base', 200, 'Hatchback'),
                (3, 'Brand', 'Three', 'Base', 300, 'Hatchback'),
                (4, 'Brand', 'One', 'Plus', 400, 'Hatchback'),
                (5, 'Brand', 'Five', 'Base', 500, 'Hatchback'),
                (6, 'Brand', 'Six', 'Base', 600, 'Hatchback')
        """)
    monkeypatch.setattr(postgres_vehicle_repository, "engine", engine)
    path = tmp_path / "vehicles.md"
    path.write_text(f"""{TABLE_HEADER}
| 4 | Brand | One | Plus | Hatchback | commuting | confirmed | City driving evidence for Plus. | Test source |
| 4 | Brand | One | Plus | Hatchback | automatic | confirmed | Plus is automatic. | Test source |
| 5 | Brand | Five | Base | Hatchback | commuting | indicative | City driving potential. | Test source |
| 5 | Brand | Five | Base | Hatchback | parking | indicative | Parking potential. | Test source |
| 6 | Brand | Six | Old trim | Hatchback | automatic | confirmed | Old trim is automatic. | Test source |
| 7 | Brand | Seven | Base | Hatchback | commuting | confirmed | Removed variant. | Test source |
""", encoding="utf-8")
    tools = AgentTools()
    tools.recommendation_service = RecommendationService(
        tools.vehicle_service.repository, FixtureIndex(VehicleKnowledge(path)),
    )
    yield tools
    engine.dispose()


def tool(tools, name):
    return next(tool for tool in tools.get_tools() if tool.name == name)


def recommend(tools, preferences=(), required_topics=(), **filters):
    return tool(tools, "recommend_vehicles").invoke({
        "request": {"preferences": list(preferences), "required_topics": list(required_topics),
                    "filters": filters or None},
    })


def ids(results):
    return [item["vehicle"]["id"] for item in results]


def test_sql_only_search_keeps_vehicles_without_markdown(tools):
    result = tool(tools, "search_vehicles").invoke({"request": {"max_price": 500}})
    assert [vehicle.id for vehicle in result] == [1, 2, 3]


def test_kb_led_fetches_exact_ids_once_and_omits_missing_row(tools):
    repository = tools.vehicle_service.repository
    with patch.object(repository, "get_by_ids", wraps=repository.get_by_ids) as lookup:
        result = recommend(tools, ["easy in narrow city streets"])["recommendations"]
    lookup.assert_called_once_with([4, 5, 7])
    assert ids(result) == [4, 5]
    assert result[0]["vehicle"]["price"] == 400
    assert result[0]["vehicle"]["variant"] == "Plus"
    assert result[0]["evidence"][0]["source"] == "Test source"


def test_combined_limits_semantic_search_to_all_sql_candidates(tools):
    knowledge = tools.recommendation_service.knowledge
    repository = tools.vehicle_service.repository
    with (
        patch.object(repository, "get_by_ids") as lookup,
        patch.object(knowledge, "semantic_matches", wraps=knowledge.semantic_matches) as query,
    ):
        result = recommend(tools, ["easy in narrow city streets"], max_price=450)["recommendations"]
    lookup.assert_not_called()
    query.assert_called_once_with(["easy in narrow city streets"], [1, 2, 3, 4])
    assert ids(result) == [4]
    assert result[0]["match"] == "budget_match"


def test_budget_match_can_include_indicative_evidence(tools):
    result = recommend(tools, ["easy in narrow city streets"], min_price=500, max_price=500)["recommendations"]
    assert ids(result) == [5]
    assert result[0]["match"] == "budget_match"
    assert result[0]["evidence"][0]["strength"] == "indicative"


def test_firm_requirement_excludes_unverified_and_stale_variants(tools):
    required = ["automatic"]
    assert ids(recommend(tools, required_topics=required, max_price=650)["recommendations"]) == [4]
    assert recommend(tools, required_topics=required, max_price=399)["status"] == "requirements_unverified"
    assert ids(recommend(tools, ["easy in narrow city streets"], required, max_price=650)["recommendations"]) == [4]
    assert ids(recommend(tools, ["smooth automatic driving"], max_price=650)["recommendations"]) == [4]


def test_weak_evidence_asks_for_clarification_and_priority_order_breaks_ties(tools):
    result = recommend(tools, ["premium sound system"], max_price=450)
    assert result == {"status": "clarification_needed", "recommendations": []}
    result = recommend(tools, ["easy in narrow city streets", "close parking"])
    assert ids(result["recommendations"]) == [5, 4]
    assert result["recommendations"][1]["matched_preferences"] == ["easy in narrow city streets"]


def test_inventory_failure_differs_from_no_matches(tools, monkeypatch):
    recommendation = tool(tools, "recommend_vehicles")
    args = {"request": {"preferences": ["easy in narrow city streets"], "filters": {"max_price": 1}}}
    assert recommendation.invoke(args) == {"status": "no_catalogue_matches", "recommendations": []}

    def unavailable(request):
        raise OperationalError("private SQL", {}, RuntimeError("private connection details"))

    monkeypatch.setattr(tools.vehicle_service.repository, "search_candidates", unavailable)
    assert recommendation.invoke(args) == "Inventory is temporarily unavailable."


def test_markdown_rejects_conflicting_variant_identity(tmp_path):
    path = tmp_path / "invalid.md"
    path.write_text(f"""{TABLE_HEADER}
| 9 | Brand | One | Base | Hatchback | commuting | indicative | A reason. | Source |
| 9 | Brand | One | Plus | Hatchback | parking | indicative | A reason. | Source |
""", encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting vehicle ID"):
        VehicleKnowledge(path)


def test_seeded_inventory_batch_lookup_and_candidate_search():
    repository = postgres_vehicle_repository.PostgresVehicleRepository()
    knowledge = VehicleKnowledge()
    entries_by_id = knowledge.retrieve(["commuting"])
    vehicles = repository.get_by_ids(list(entries_by_id))
    assert {vehicle.id for vehicle in vehicles} == set(entries_by_id)
    assert all(
        "commuting" in verified_evidence(vehicle, entries_by_id[vehicle.id])
        for vehicle in vehicles
    )
    candidates = repository.search_candidates(SearchRequest(
        brand="Maruti Suzuki", model="Swift", max_price=800000,
    ))
    assert [vehicle.id for vehicle in candidates] == [131, 132, 133, 134]


def test_completed_shortlist_is_restored_in_order_for_follow_up(tools):
    class FollowUpModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if messages[-1].content == "What was the second one?":
                saved = next(message for message in messages if isinstance(message, ToolMessage))
                results = json.loads(saved.content)["recommendations"]
                assert ids(results) == [4, 5]
                assert results[1]["evidence"][0]["reason"] == "City driving potential."
            return super()._generate(messages, stop, run_manager, **kwargs)

    model = FollowUpModel(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "recommend_vehicles", "id": "recommendation",
            "args": {"request": {"preferences": ["easy in narrow city streets"]}},
        }]),
        AIMessage(content="1. One Plus (ID 4).\n2. Five Base (ID 5)."),
        AIMessage(content="The second one was Five Base (ID 5)."),
    ])
    agent = create_agent(model, tools=tools.get_tools())
    limiter.reset()
    app.dependency_overrides[get_agent] = lambda: agent
    try:
        with TestClient(app) as client:
            first = client.post("/api/chat", json={"message": "Suggest an easy commuter."})
            assert first.status_code == 200
            second = client.post("/api/chat", json={
                "message": "What was the second one?", "session_id": first.json()["session_id"],
            })
            assert second.status_code == 200
            assert second.json()["reply"] == "The second one was Five Base (ID 5)."
    finally:
        app.dependency_overrides.pop(get_agent)
        limiter.reset()
