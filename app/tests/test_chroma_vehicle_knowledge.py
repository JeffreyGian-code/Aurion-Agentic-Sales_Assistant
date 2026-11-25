import os

import httpx
import pytest

from app.repositories.chroma_vehicle_knowledge import ChromaVehicleKnowledge
from app.repositories.vehicle_knowledge import TABLE_HEADER, VehicleKnowledge
from app.services.embedding_service import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, OpenRouterEmbeddings
from app.tools.agent_tools import AgentTools


def test_chroma_failure_surfaces_as_a_tool_error(monkeypatch):
    from app.tools import agent_tools

    def unavailable(request):
        raise httpx.ConnectError("private connection detail", request=request)

    monkeypatch.setattr(agent_tools, "ChromaVehicleKnowledge", lambda entries: ChromaVehicleKnowledge(
        entries, transport=httpx.MockTransport(unavailable),
    ))
    tool = next(tool for tool in AgentTools().get_tools() if tool.name == "recommend_vehicles")
    result = tool.invoke({"request": {"preferences": ["easy to park"]}})
    assert result == "Vehicle recommendation evidence is temporarily unavailable."


@pytest.mark.skipif(os.getenv("RUN_CHROMA_INTEGRATION") != "1", reason="requires Docker Chroma")
def test_running_chroma_searches_vectors_with_catalogue_id_filter(tmp_path):
    class FixtureEmbeddings:
        def embed(self, texts, *, mode):
            return [[1.0, 0.0] if "city" in phrase or "narrow streets" in phrase else [0.0, 1.0]
                    for phrase in texts]

    path = tmp_path / "fixture.md"
    path.write_text(f"""{TABLE_HEADER}
| 101 | Fixture | One | Base | Hatchback | commuting | indicative | city driving | Test source |
| 102 | Fixture | Two | Plus | Sedan | luggage | indicative | separate boot | Test source |
| 102 | Fixture | Two | Plus | Sedan | automatic | confirmed | automatic transmission | Test source |
""", encoding="utf-8")
    entries = VehicleKnowledge(path).all_entries()
    embeddings = FixtureEmbeddings()
    assert ChromaVehicleKnowledge(entries, embeddings=embeddings).build() == 3
    knowledge = ChromaVehicleKnowledge(entries, embeddings=embeddings)
    group, = knowledge.semantic_matches(["narrow streets"], [101, 102])
    assert group[0].entry.id == 101
    assert group[0].similarity == pytest.approx(1)
    restricted, = knowledge.semantic_matches(["narrow streets"], [102])
    assert {hit.entry.id for hit in restricted} == {102}
    assert all(hit.similarity == pytest.approx(0) for hit in restricted)
    assert [entry.id for entry in knowledge.requirement_entries(["automatic"])] == [102]


def test_embedding_provider_payload_and_failure(monkeypatch):
    import json

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    vectors = [[1.0] * EMBEDDING_DIMENSIONS, [0.5] * EMBEDDING_DIMENSIONS]
    calls = []

    def endpoint(request):
        calls.append(json.loads(request.content))
        if len(calls) == 2:
            return httpx.Response(429, json={"error": "private provider failure"})
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": vectors[1]}, {"index": 0, "embedding": vectors[0]},
        ]})

    from app.services.embedding_service import EmbeddingError

    service = OpenRouterEmbeddings(httpx.MockTransport(endpoint))
    assert service.embed(["passage A", "passage B"], mode="passage") == vectors
    assert calls[0] == {"model": EMBEDDING_MODEL, "input": ["passage A", "passage B"],
                        "input_type": "passage", "encoding_format": "float"}
    with pytest.raises(EmbeddingError, match="temporarily unavailable"):
        service.embed(["compact for narrow streets"], mode="query")
    assert calls[1]["input_type"] == "query"


def test_personal_contact_details_are_rejected_before_retrieval():
    tool = next(tool for tool in AgentTools().get_tools() if tool.name == "recommend_vehicles")
    result = tool.invoke({"request": {"preferences": ["parking near test@example.com"]}})
    assert "without personal details" in result
