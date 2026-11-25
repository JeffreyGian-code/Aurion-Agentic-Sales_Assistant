import os

import httpx
import pytest

from app.repositories.chroma_vehicle_knowledge import ChromaVehicleKnowledge
from app.repositories.vehicle_knowledge import VehicleKnowledge
from app.tools.agent_tools import AgentTools


def test_chroma_failure_surfaces_as_a_tool_error(monkeypatch):
    from app.tools import agent_tools

    def unavailable(request):
        raise httpx.ConnectError("private connection detail", request=request)

    monkeypatch.setattr(agent_tools, "ChromaVehicleKnowledge", lambda entries: ChromaVehicleKnowledge(
        entries, transport=httpx.MockTransport(unavailable),
    ))
    tool = next(tool for tool in AgentTools().get_tools() if tool.name == "recommend_vehicles")
    result = tool.invoke({"request": {"priorities": [{"topic": "parking"}]}})
    assert result == "Vehicle recommendation evidence is temporarily unavailable."


@pytest.mark.skipif(os.getenv("RUN_CHROMA_INTEGRATION") != "1", reason="requires Docker Chroma")
def test_running_chroma_retrieves_markdown_by_topic_and_variant():
    entries = VehicleKnowledge().all_entries()
    knowledge = ChromaVehicleKnowledge(entries)
    parking_ids = {entry.id for entry in entries if entry.evidence.topic == "parking"}
    assert set(knowledge.retrieve(["parking"])) == parking_ids
    assert knowledge.retrieve(["unmapped_topic"]) == {}
    result = knowledge.entries_for_ids([131, 2147483647])
    assert {entry.evidence.topic for entry in result[131]} == {"commuting", "parking"}
    assert set(result) == {131}

    tools = AgentTools()
    tool = next(tool for tool in tools.get_tools() if tool.name == "recommend_vehicles")
    response = tool.invoke({"request": {
        "priorities": [{"topic": "commuting"}],
        "filters": {"brand": "Maruti Suzuki", "max_price": 799999},
    }})
    first = response["recommendations"][0]
    assert (first["vehicle"]["id"], first["vehicle"]["price"]) == (131, 650000)
    assert first["evidence"][0]["topic"] == "commuting"
