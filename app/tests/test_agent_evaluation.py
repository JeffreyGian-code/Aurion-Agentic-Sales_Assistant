"""Opt-in real-model evals plus an offline check of the evaluation harness."""

from decimal import Decimal
import os
import re
from time import perf_counter, sleep
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import tracing_context
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.models.SearchRequest import SearchRequest
from app.tests.evaluation import CATALOGUE, FAILURE_MARKER, evaluation_cases


CORE_CASES = (
    "strict-budget", "price-range", "descending-price", "exact-variant", "details-found",
    "emi-complete", "emi-down-payment", "emi-missing-inputs", "retain-budget",
    "resolve-reference", "general-question", "unsupported-mileage", "empty-search",
    "repository-failure",
)
BATCHES = {
    "core": CORE_CASES,
    "extended": tuple(name for name in evaluation_cases if name not in CORE_CASES),
    "all": (*CORE_CASES, *(name for name in evaluation_cases if name not in CORE_CASES)),
}


def selected_cases():
    if os.getenv("RUN_AGENT_EVALS") != "1":
        return tuple(evaluation_cases)
    batch = os.getenv("AGENT_EVAL_BATCH", "core")
    if batch not in BATCHES:
        raise pytest.UsageError("AGENT_EVAL_BATCH must be core, extended, or all.")
    return BATCHES[batch]


class OpenRouterRequestBudget:
    """Meter outbound attempts at the HTTP boundary, including failed requests."""

    limit = 30
    interval_seconds = 4

    def __init__(self):
        self.sent = 0
        self.next_send = 0.0
        self.rate_limited = False

    def check(self):
        if self.rate_limited:
            pytest.skip("OpenRouter returned HTTP 429 earlier in this run")
        if self.sent >= self.limit:
            pytest.skip(f"OpenRouter request budget exhausted ({self.sent}/{self.limit})")

    def before_request(self, request):
        self.check()
        delay = self.next_send - perf_counter()
        if delay > 0:
            sleep(delay)
        self.sent += 1
        self.next_send = perf_counter() + self.interval_seconds

    def after_response(self, response):
        if response.status_code == 429:
            self.rate_limited = True
            pytest.skip("OpenRouter returned HTTP 429. Live requests stopped for this run.")


@pytest.fixture(scope="session")
def openrouter_session():
    import httpx
    from dotenv import load_dotenv

    if os.getenv("PYTEST_XDIST_WORKER"):
        raise pytest.UsageError("Run live evals in one pytest process to share the request budget.")
    load_dotenv()
    api_key = os.getenv("OPENROUTER_EVAL_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        pytest.fail("Set OPENROUTER_EVAL_API_KEY or OPENROUTER_API_KEY before running live evals.")
    budget = OpenRouterRequestBudget()
    with httpx.Client(event_hooks={
        "request": [budget.before_request],
        "response": [budget.after_response],
    }) as client:
        yield api_key, client, budget


@pytest.fixture
def catalogue(monkeypatch):
    # The repository imports a configured engine at module load. All eval
    # queries use the private fixture engine patched below.
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    from app.repositories import postgres_vehicle_repository

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE vehicles (
                    id INTEGER PRIMARY KEY, brand TEXT, model TEXT, variant TEXT,
                    price INTEGER, vehicle_type TEXT
                )
            """)
            connection.exec_driver_sql("INSERT INTO vehicles VALUES (?, ?, ?, ?, ?, ?)", CATALOGUE)
        monkeypatch.setattr(postgres_vehicle_repository, "engine", engine)
        yield
    finally:
        engine.dispose()


def normalized_arguments(name, arguments):
    if name != "search_vehicles":
        return arguments
    assert set(arguments) == {"request"}, "Search must pass a single request object"
    request = arguments["request"]
    assert set(request) <= set(SearchRequest.model_fields), "Unknown search filter"
    for bound in ("min_price", "max_price"):
        if request.get(bound) is not None:
            assert type(request[bound]) is int, "Search bounds must be whole rupees"
    filters = SearchRequest.model_validate(request).model_dump(exclude_none=True)
    return {key: value.casefold() if isinstance(value, str) else value for key, value in filters.items()}


def normalized_reply(reply):
    def lakh_to_rupees(match):
        value = format(Decimal(match[1]) * 100000, "f")
        return value.rstrip("0").rstrip(".") if "." in value else value

    reply = re.sub(r"(?<=\d),(?=\d)", "", reply)
    return re.sub(
        r"\b(\d+(?:\.\d+)?)\s*lakhs?\b",
        lakh_to_rupees,
        reply,
        flags=re.IGNORECASE,
    )


def grade_turn(messages, expected):
    calls = [call for message in messages if isinstance(message, AIMessage)
             for call in message.tool_calls]
    outputs = [message for message in messages if isinstance(message, ToolMessage)]
    expected_tools = [expected.tool] if expected.tool else []
    assert [call["name"] for call in calls] == expected_tools
    assert not any(message.invalid_tool_calls for message in messages if isinstance(message, AIMessage))
    if expected.tool:
        arguments = calls[0]["args"]
        if expected.tool == "calculate_emi":
            from app.models.emi import EMIRequest

            EMIRequest.model_validate(arguments)
        elif expected.tool == "get_vehicle_details":
            assert type(arguments.get("vehicle_id")) is int
        assert normalized_arguments(expected.tool, arguments) == normalized_arguments(
            expected.tool, expected.arguments
        )
        assert len(outputs) == 1 and outputs[0].tool_call_id == calls[0]["id"]
        if FAILURE_MARKER not in expected.forbidden:
            assert outputs[0].status == "success"
        assert not outputs[0].text.startswith("Invalid EMI request")

    assert messages and isinstance(messages[-1], AIMessage)
    reply = messages[-1].text
    assert reply.strip(), "The turn must have a customer-facing reply"
    normalized = normalized_reply(reply)
    for pattern in expected.required:
        assert re.search(pattern, normalized, re.IGNORECASE | re.DOTALL), f"Missing expected evidence: {pattern}"
    for pattern in expected.forbidden:
        assert not re.search(pattern, normalized, re.IGNORECASE | re.DOTALL), f"Unexpected evidence: {pattern}"


def run_case(agent, turns, properties):
    session_ids = {}
    for number, turn in enumerate(turns, start=1):
        thread_id = session_ids.setdefault(turn.session, uuid4().hex)
        start = perf_counter()
        try:
            with tracing_context(enabled=False):
                state = agent.invoke(
                    {"messages": [HumanMessage(content=turn.prompt)]},
                    config={"configurable": {"thread_id": thread_id}},
                )
        except Exception as exc:
            # Suppress exception details, which may contain connection info.
            raise pytest.fail.Exception(
                f"Turn {number}: agent raised {type(exc).__name__} before replying", pytrace=False
            ) from None
        finally:
            properties.append((f"turn_{number}_seconds", round(perf_counter() - start, 3)))

        history = state["messages"]
        last_user = max(index for index, message in enumerate(history) if isinstance(message, HumanMessage))
        messages = history[last_user + 1:]
        model_messages = [message for message in messages if isinstance(message, AIMessage)]
        properties.append((f"turn_{number}_model_messages", len(model_messages)))
        properties.append((f"turn_{number}_tool_calls", sum(len(message.tool_calls) for message in model_messages)))
        if model_messages and all(message.usage_metadata for message in model_messages):
            properties.append((f"turn_{number}_tokens", sum(
                message.usage_metadata["total_tokens"] for message in model_messages
            )))
        print(f"Turn {number} [{turn.session}]: {turn.prompt}")
        for message in model_messages:
            if message.tool_calls:
                print(f"Tool calls: {[(call['name'], call['args']) for call in message.tool_calls]}")
        if model_messages:
            print(f"Reply: {model_messages[-1].text}")
        grade_turn(messages, turn)


@pytest.mark.skipif(os.getenv("RUN_AGENT_EVALS") != "1", reason="requires opt-in real model calls")
@pytest.mark.parametrize("case_name", selected_cases())
def test_live_agent(case_name, catalogue, monkeypatch, request, openrouter_session):
    from openrouter import OpenRouter

    api_key, http_client, budget = openrouter_session
    budget.check()
    monkeypatch.setenv("OPENROUTER_API_KEY", api_key)
    from app.agents.agent import agent, model

    client = OpenRouter(
        api_key=api_key,
        client=http_client,
        server_url=model.openrouter_api_base,
        retry_config=None,
        timeout_ms=model.request_timeout,
    )
    monkeypatch.setattr(model, "client", client)

    if case_name == "repository-failure":
        from app.repositories.postgres_vehicle_repository import PostgresVehicleRepository

        def failing_search(self, **filters):
            raise ConnectionError(FAILURE_MARKER)

        monkeypatch.setattr(PostgresVehicleRepository, "search", failing_search)

    before = budget.sent
    try:
        run_case(agent, evaluation_cases[case_name], request.node.user_properties)
    finally:
        request.node.user_properties.extend([
            ("openrouter_requests", budget.sent - before),
            ("openrouter_requests_this_run", budget.sent),
            ("openrouter_rate_limited", budget.rate_limited),
        ])


def test_eval_harness_checks_tools_and_reply(catalogue):
    from app.tools.agent_tools import AgentTools

    class ScriptedModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    call = AIMessage(content="", tool_calls=[{
        "name": "search_vehicles",
        "args": {"request": {"brand": "honda", "vehicle_type": "sedan", "max_price": 999999}},
        "id": "fixture-call",
    }])
    for reply, should_pass in [
        ("Amaze S (ID 3): ₹8 lakh. City VX (ID 1): ₹9,50,000. Indicative prices.", True),
        ("Amaze S (ID 3): ₹8 lakh. City ZX (ID 2): ₹9,50,000.", False),
    ]:
        graph = create_agent(
            ScriptedModel(responses=[call, AIMessage(content=reply)]),
            tools=AgentTools().get_tools(),
            checkpointer=InMemorySaver(),
        )
        if should_pass:
            run_case(graph, evaluation_cases["strict-budget"], [])
        else:
            with pytest.raises(AssertionError, match="Unexpected evidence"):
                run_case(graph, evaluation_cases["strict-budget"], [])
