import os
import logging
import sqlite3
import uuid
from fastapi import Request
from fastapi.responses import JSONResponse

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.rate_limit import limiter, rate_limit_exceeded_handler
from app.api.routes import chat, health

load_dotenv()

DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://localhost:5173"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vehicle Sales Assistant API",
        version="1.0.0",
    )

    # Per-IP rate limiting on POST /api/chat (see rate_limit.py).
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


    @app.exception_handler(sqlite3.Error)
    async def storage_error(request: Request, exc: sqlite3.Error):
        logging.getLogger(__name__).error("Storage failure %s (%s)", request.state.request_id, type(exc).__name__)
        return JSONResponse({"detail": "Conversation storage is temporarily unavailable."}, status_code=503)

    @app.middleware("http")
    async def correlate(request, call_next):
        request.state.request_id = uuid.uuid4().hex
        try:
            response = await call_next(request)
        except Exception as exc:
            logging.getLogger(__name__).error("Request %s failed (%s)", request.state.request_id, type(exc).__name__)
            response = JSONResponse({"detail": "Something went wrong while processing your request."}, status_code=500)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
        if origin.strip()
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        expose_headers=["Retry-After", "X-Error-Code", "X-Request-ID"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Chat and health routes. Vehicle search/details and EMI are agent tools,
    # reached through /api/chat, not separate endpoints.
    for router in (health.router, chat.router):
        app.include_router(router, prefix="/api")

    return app


app = create_app()
