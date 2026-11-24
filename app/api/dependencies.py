import logging
import os
from functools import lru_cache

from fastapi import HTTPException


@lru_cache
def get_agent():
    try:
        if not os.getenv("OPENROUTER_API_KEY", "").strip():
            raise ValueError("Missing provider configuration")
        from app.agents.agent import build_agent
        return build_agent()
    except Exception as exc:
        logging.getLogger(__name__).error("Chat initialization failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Chat is temporarily unavailable.") from exc
