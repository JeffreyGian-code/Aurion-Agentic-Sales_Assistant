# app/database.py

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    **({"connect_args": {"connect_timeout": 4, "options": "-c statement_timeout=8000"}, "pool_timeout": 5} if DATABASE_URL.startswith("postgresql") else {}),
)