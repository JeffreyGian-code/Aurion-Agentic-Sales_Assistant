from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Literal


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    request_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    message: str = Field(min_length=1, max_length=2000)
    reset_context: bool = False
    session_id: str | None = Field(
        default=None, pattern=r"^[a-zA-Z0-9_-]{1,80}$",
        description="Conversation id. Omit to start a new conversation.",
    )


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class ChatProgress(BaseModel):
    phase: Literal["processing", "tool_started", "tool_finished", "tool_failed", "writing"]
    label: str
    run_id: str | None = None
    tool: str | None = None
    input: Any = None
    output: Any = None
    duration_ms: float | None = None

