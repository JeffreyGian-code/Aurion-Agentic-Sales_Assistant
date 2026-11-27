import logging
import asyncio
import json
from contextlib import aclosing, suppress
import uuid
from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.dependencies import get_agent
from app.api.chat_usage import TURN_TIMEOUT_SECONDS, owned_usage, begin, finish
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.messages import BaseMessage, messages_from_dict
import sqlite3
from app.api.rate_limit import CHAT_LIMIT, limiter
from app.api.schemas import ChatProgress, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/usage/{session_id}")
def usage(session_id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9_-]{1,80}$")], request: Request):
    return {key: value for key, value in owned_usage(session_id, request.cookies.get("vehicle_owner")).items() if key != "thread_id"}


def final_reply(result):
    messages = result.get("messages") if isinstance(result, dict) else None
    last = messages[-1] if isinstance(messages, list) and messages else None
    content = getattr(last, "content", None)
    if getattr(last, "type", "ai") != "ai":
        content = None
    if isinstance(content, list):
        content = "".join(p["text"] for p in content if isinstance(p, dict) and
                          p.get("type") == "text" and isinstance(p.get("text"), str))
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(502, "The assistant returned an incomplete reply. Please retry.")
    return content


class Turn:
    async def start(self, body, request):
        self.id = body.request_id or uuid.uuid4().hex
        owner = request.cookies.get("vehicle_owner") if "headers" in request.scope else None
        session = body.session_id
        self.request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        self.session, self.lease, history, self.cached, thread, self.owner = await asyncio.to_thread(
            begin, session, body.message, body.reset_context, self.id, owner)
        try:
            self.messages = messages_from_dict(history) + [{"role": "user", "content": body.message}]
        except (KeyError, ValueError, TypeError) as exc:
            await self.close()
            raise HTTPException(503, "Saved context could not be loaded. Reset the conversation to continue.") from exc
        self.config = {"configurable": {"thread_id": thread}}

    async def complete(self, result):
        reply = final_reply(result)
        messages = result["messages"]
        history = [{"type": m.type, "data": m.model_dump(mode="json")}
                   for m in messages if isinstance(m, BaseMessage)]
        await asyncio.to_thread(finish, self.session, self.lease, self.id, history, reply)
        self.lease = None
        return reply

    async def close(self):
        if self.lease:
            await asyncio.shield(asyncio.to_thread(finish, self.session, self.lease, self.id))


def failure(exc, request_id):
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ModelCallLimitExceededError):
        return HTTPException(429, "The processing limit was reached. Please try a simpler query.",
                             headers={"X-Error-Code": "conversation-limit"})
    if isinstance(exc, TimeoutError):
        return HTTPException(504, "The assistant timed out. Please retry.")
    if isinstance(exc, sqlite3.Error):
        return HTTPException(503, "Conversation storage is temporarily unavailable.")
    logger.error("Chat request %s failed (%s)", request_id, type(exc).__name__)
    return HTTPException(500, "Something went wrong while processing your request.")


def remember(response, turn, request):
    response.set_cookie("vehicle_owner", turn.owner, httponly=True, samesite="lax",
                        secure=request.scope.get("scheme") == "https", max_age=365*86400)
    return response


@router.post("", response_model=ChatResponse)
@limiter.shared_limit(CHAT_LIMIT, scope="chat")
async def chat(request: Request, body: ChatRequest, agent: Annotated[Any, Depends(get_agent)]):
    turn = Turn()
    await turn.start(body, request)
    try:
        reply = turn.cached
        if reply is None:
            async with asyncio.timeout(TURN_TIMEOUT_SECONDS):
                payload = {"messages": turn.messages}
                result = (await agent.ainvoke(payload, config=turn.config) if hasattr(agent, "ainvoke")
                          else await asyncio.to_thread(agent.invoke, payload, config=turn.config))
                reply = await turn.complete(result)
        return remember(JSONResponse({"reply": reply, "session_id": turn.session}), turn, request)
    except Exception as exc:
        error = failure(exc, turn.request_id)
        return remember(JSONResponse({"detail": error.detail}, status_code=error.status_code, headers=error.headers), turn, request)
    finally:
        await turn.close()


TOOL_LABELS = {
    "search_vehicles": "Searching vehicle inventory…",
    "recommend_vehicles": "Comparing vehicle recommendations…",
    "get_vehicle_details": "Fetching vehicle details…",
    "describe_vehicle": "Reading the vehicle guide…",
    "compare_higher_trims": "Comparing available trims…",
    "calculate_emi": "Calculating EMI…",
}
STREAM_HEARTBEAT_SECONDS = 15


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


TRACE_FIELDS = {
    "request", "vehicles", "brand", "model", "variant", "vehicle_type", "min_price",
    "max_price", "sort_order", "vehicle_id", "id", "price", "principal", "annual_rate",
    "months", "monthly_emi", "total_payment", "total_interest",
    "filters", "recommendations", "vehicle", "match", "status",
}


def _trace_value(value, *, field=None):
    if hasattr(value, "content"):
        value = value.content
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _trace_value(item, field=key) for key, item in value.items() if key in TRACE_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_trace_value(item) for item in value[:10]]
    if isinstance(value, str):
        if field in {"brand", "model", "variant", "vehicle_type", "sort_order", "match", "status"}:
            return value[:120]
        try:
            parsed = json.loads(value)
        except ValueError:
            return None
        if isinstance(parsed, (dict, list)):
            return _trace_value(parsed)
        return None
    return value if isinstance(value, (int, float, bool)) else None


class ChatStreamResponse(StreamingResponse):
    async def stream_response(self, send):
        try:
            await super().stream_response(send)
        finally:
            # Also close the generator when an ASGI 2.4 send raises on disconnect.
            await self.body_iterator.aclose()


@router.post("/stream")
@limiter.shared_limit(CHAT_LIMIT, scope="chat")
async def stream_chat(
    request: Request,
    body: ChatRequest,
    agent: Annotated[Any, Depends(get_agent)],
) -> StreamingResponse:
    turn = Turn()
    await turn.start(body, request)
    session_id = turn.session

    async def events():
        # One queue and task per request: no callbacks or status shared across users.
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)

        async def produce():
            try:
                writing = False
                tool_starts: dict[str, float] = {}
                async for event in agent.astream_events(
                    {"messages": turn.messages},
                    config=turn.config,
                    version="v2",
                ):
                    kind = event["event"]
                    name = event.get("name", "")
                    run_id = str(event.get("run_id", ""))
                    progress = None
                    if kind == "on_chat_model_start":
                        if writing:
                            # A tool round-trip starts a new answer; replace any preamble.
                            await queue.put(("delta", {"text": "", "reset": True}))
                        writing = False
                        progress = ChatProgress(phase="processing", label="Processing your request…")
                    elif kind == "on_tool_start":
                        tool_starts[run_id] = perf_counter()
                        progress = ChatProgress(
                            phase="tool_started", label=TOOL_LABELS.get(name, f"Calling {name}…"),
                            run_id=run_id, tool=name,
                            input=_trace_value(event.get("data", {}).get("input")),
                        )
                    elif kind in {"on_tool_end", "on_tool_error"}:
                        if getattr(event.get("data", {}).get("output"), "status", None) == "error":
                            kind = "on_tool_error"
                        tool_started = tool_starts.pop(run_id, None)
                        progress = ChatProgress(
                            phase="tool_finished" if kind == "on_tool_end" else "tool_failed",
                            label="Processing tool results…" if kind == "on_tool_end" else "Tool failed; processing the result…",
                            run_id=run_id, tool=name,
                            duration_ms=(max(0, (perf_counter() - tool_started) * 1000)
                                         if tool_started is not None else None),
                            output=(_trace_value(event.get("data", {}).get("output"))
                                    if kind == "on_tool_end" else "The tool could not complete this step."),
                        )
                    elif kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        content = getattr(chunk, "content", None)
                        # Only text content counts; tool arguments/reasoning are not a reply.
                        text = content if isinstance(content, str) else "".join(
                            part.get("text", "")
                            for part in (content or [])
                            if isinstance(part, dict) and part.get("type") == "text"
                        )
                        if text:
                            if not writing:
                                writing = True
                                await queue.put(("progress", ChatProgress(
                                    phase="writing", label="Writing a response…",
                                ).model_dump()))
                            await queue.put(("delta", {"text": text}))
                    elif kind == "on_chain_end" and not event.get("parent_ids"):
                        result = event.get("data", {}).get("output", {})
                        reply = await turn.complete(result)
                        await queue.put(("completed", ChatResponse(
                            reply=reply, session_id=session_id,
                        ).model_dump()))
                        return
                    if progress:
                        await queue.put(("progress", progress.model_dump()))
                raise RuntimeError("Agent stream ended without a final result")
            except Exception as exc:
                error = failure(exc, turn.request_id)
                await queue.put(("error", {"status": error.status_code, "detail": error.detail,
                                           "code": (error.headers or {}).get("X-Error-Code")}))

        yield _sse("started", {"session_id": session_id})
        if turn.cached is not None:
            yield _sse("completed", {"session_id": session_id, "reply": turn.cached})
            return
        task = asyncio.create_task(produce())
        deadline = asyncio.get_running_loop().time() + TURN_TIMEOUT_SECONDS
        try:
            while True:
                if asyncio.get_running_loop().time() >= deadline:
                    yield _sse("error", {"status": 504, "detail": "The assistant timed out. Please retry."})
                    break
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=min(STREAM_HEARTBEAT_SECONDS, max(0, deadline - asyncio.get_running_loop().time())))
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield _sse(event, data)
                if event in {"completed", "error"}:
                    break
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def guarded():
        try:
            async with aclosing(events()) as source:
                async for frame in source:
                    yield frame
        finally:
            await turn.close()

    return remember(ChatStreamResponse(guarded(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    }), turn, request)
