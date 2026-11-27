import json
import os
from unittest.mock import Mock

import httpx
import pytest

from app.RAG.retrieval.chroma_vehicle_knowledge import ChromaKnowledgeError, ChromaVehicleKnowledge
from app.RAG.ingestion.vehicle_knowledge import VehicleKnowledge
from app.RAG.embeddings.embedding_service import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, OpenRouterEmbeddings
from app.tools.agent_tools import AgentTools


COLLECTION_ID = "fbb94eb4-115d-4a82-bbd4-3fc4cc152c44"


FIXTURE_MARKDOWN = """## Fixture One
A compact hatchback for narrow streets and city driving.

### Seeded catalogue variants
- **ID 101 — Fixture One Base** · Hatchback · ₹100

## Fixture Two
The sedan has a separate boot.

### Seeded catalogue variants
- **ID 102 — Fixture Two Plus** · Sedan · ₹200

### Verified catalogue equipment
- **ID 102 · automatic · present**. Automatic transmission. [Source](https://fixture.example/plus)
"""


@pytest.fixture
def parsed_evidence(tmp_path):
    path = tmp_path / "knowledge.md"
    path.write_text(FIXTURE_MARKDOWN, encoding="utf-8")
    return VehicleKnowledge(path).all_entries()


def test_build_upserts_passage_vectors_and_reuses_complete_collection(parsed_evidence):
    stored = {}
    embeddings = Mock()
    embeddings.embed.return_value = [[0.6, 0.8], [1.0, 0.0]]

    def endpoint(request):
        if request.method == "POST" and request.url.path.endswith("/collections"):
            payload = json.loads(request.content)
            assert payload == {"name": knowledge.collection_name, "get_or_create": True,
                               "configuration": {"hnsw": {"space": "cosine"}}}
            return httpx.Response(200, json={"id": COLLECTION_ID})
        if request.method == "GET" and request.url.path.endswith(f"/{COLLECTION_ID}/count"):
            return httpx.Response(200, json=len(stored.get("ids", [])))
        assert request.method == "POST" and request.url.path.endswith(f"/{COLLECTION_ID}/upsert")
        stored.update(json.loads(request.content))
        return httpx.Response(200, json={})

    knowledge = ChromaVehicleKnowledge(parsed_evidence, embeddings=embeddings,
                                       transport=httpx.MockTransport(endpoint))
    assert knowledge.build() == knowledge.build() == 2
    passages = [entry.passage for entry in parsed_evidence]
    embeddings.embed.assert_called_once_with(passages, mode="passage")
    assert stored["ids"] == ["vehicle:101", "vehicle:102"]
    assert stored["documents"] == passages
    assert stored["embeddings"] == embeddings.embed.return_value
    assert stored["metadatas"][1]["id"] == 102
    assert stored["metadatas"][1]["topic"] == "vehicle_description"
    assert json.loads(stored["metadatas"][1]["facts"])[0]["topic"] == "automatic"


def test_retrieval_embeds_queries_and_fetches_exact_ids_for_requirements(parsed_evidence):
    automatic = parsed_evidence[1]
    row = {
        **automatic.model_dump(exclude={"evidence", "facts", "trim_rank"}),
        **automatic.evidence.model_dump(),
        "trim_rank": 0,
        "facts": json.dumps([fact.model_dump() for fact in automatic.facts]),
    }
    embeddings = Mock()
    embeddings.embed.return_value = [[0.0, 1.0]]

    def endpoint(request):
        if request.method == "GET":
            body = 2 if request.url.path.endswith("/count") else {"id": COLLECTION_ID}
        elif request.url.path.endswith(f"/{COLLECTION_ID}/query"):
            assert json.loads(request.content) == {
                "query_embeddings": [[0.0, 1.0]], "where": {"id": {"$in": [102]}},
                "n_results": 2, "include": ["metadatas", "distances"],
            }
            body = {"metadatas": [[row]], "distances": [[0.25]]}
        else:
            assert request.url.path.endswith(f"/{COLLECTION_ID}/get")
            assert json.loads(request.content) == {
                "ids": ["vehicle:102"],
                "include": ["metadatas"],
            }
            body = {"metadatas": [row]}
        return httpx.Response(200, json=body)

    knowledge = ChromaVehicleKnowledge(parsed_evidence, embeddings=embeddings,
                                       transport=httpx.MockTransport(endpoint))
    assert knowledge.semantic_matches(["easy to drive"], []) == [[]]
    (hit,), = knowledge.semantic_matches(["easy to drive"], [102])
    assert hit.entry == automatic
    assert hit.similarity == pytest.approx(0.75)
    assert knowledge.requirement_entries(["automatic"]) == [automatic]
    embeddings.embed.assert_called_once_with(["easy to drive"], mode="query")


def test_retriever_rejects_an_incomplete_collection_before_embedding(parsed_evidence):
    def endpoint(request):
        body = 1 if request.url.path.endswith("/count") else {"id": COLLECTION_ID}
        return httpx.Response(200, json=body)

    embeddings = Mock()
    knowledge = ChromaVehicleKnowledge(parsed_evidence, embeddings=embeddings,
                                       transport=httpx.MockTransport(endpoint))
    with pytest.raises(ChromaKnowledgeError, match="index is incomplete"):
        knowledge.semantic_matches(["easy to park"], None)
    embeddings.embed.assert_not_called()


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
    path.write_text(FIXTURE_MARKDOWN, encoding="utf-8")
    entries = VehicleKnowledge(path).all_entries()
    embeddings = FixtureEmbeddings()
    assert ChromaVehicleKnowledge(entries, embeddings=embeddings).build() == 2
    knowledge = ChromaVehicleKnowledge(entries, embeddings=embeddings)
    group, = knowledge.semantic_matches(["narrow streets"], [101, 102])
    assert group[0].entry.id == 101
    assert group[0].similarity == pytest.approx(1)
    restricted, = knowledge.semantic_matches(["narrow streets"], [102])
    assert {hit.entry.id for hit in restricted} == {102}
    assert all(hit.similarity == pytest.approx(0) for hit in restricted)
    assert [entry.id for entry in knowledge.requirement_entries(["automatic"])] == [102]


def test_embedding_provider_payload_and_failure(monkeypatch):
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

    from app.RAG.embeddings.embedding_service import EmbeddingError

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
