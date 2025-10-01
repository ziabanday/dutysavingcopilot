# app/db/session.py
"""
Session/engine factory for Postgres (Supabase) with safe defaults.
- Loads .env
- Prefers DATABASE_URL (postgresql+psycopg://... ?sslmode=require)
- Exposes: engine, get_session(), ping()
- NEVER calls create_all()
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from dotenv import load_dotenv

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

# 1) Load .env early
load_dotenv(override=False)

# 2) Build DATABASE_URL if not present (fallback from discrete vars)
def _build_url_from_parts() -> Optional[str]:
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    user = os.getenv("POSTGRES_USER")
    pwd = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB", "postgres")
    if not (host and port and user and pwd):
        return None
    # force sslmode=require
    return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{db}?sslmode=require"

DATABASE_URL = os.getenv("DATABASE_URL") or _build_url_from_parts()
if not DATABASE_URL:
    raise RuntimeError(
        "No DATABASE_URL and insufficient POSTGRES_* vars. "
        "Set DATABASE_URL in .env (use Session Pooler 6543) or complete POSTGRES_*."
    )

# 3) Ensure sslmode=require is present
if "sslmode=" not in DATABASE_URL:
    sep = "&" if ("?" in DATABASE_URL) else "?"
    DATABASE_URL = f"{DATABASE_URL}{sep}sslmode=require"

# 4) Engine & session factory
engine: Engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    future=True,
)

_SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

@contextmanager
def get_session() -> Iterator[Session]:
    """Context-managed SQLAlchemy Session."""
    session: Session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()

def ping(timeout_seconds: int = 5) -> bool:
    """True if we can connect and run a trivial query."""
    try:
        with engine.connect() as conn:
            conn.execution_options(stream_results=False)
            conn.exec_driver_sql("SET statement_timeout = %s;" % (timeout_seconds * 1000))
            conn.execute(text("SELECT 1;"))
        return True
    except Exception as e:
        # Print once to help CLI diagnostics; raise again for callers if needed
        print("DB ping error:", repr(e))
        return False
