# app/core/settings.py
from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv

# Load .env from the repo root
load_dotenv()

# Messages / constants
DISCLAIMER_TEXT = "Not legal advice. Verify with a licensed customs broker or counsel."
# Back-compat for earlier misspelling, if anything imports it
DISLCAIMER_TEXT = DISCLAIMER_TEXT  # noqa: N816

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# Guardrails
MAX_MONTHLY_TOKENS = int(os.getenv("MAX_MONTHLY_TOKENS", "1000000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# CORS
CORS_ORIGINS: List[str] = [
    o for o in os.getenv("CORS_ORIGINS", "http://localhost:8501").split(",") if o
]

# DB (wired later)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Paths
BUDGET_DIR = os.path.join(os.getcwd(), "budget")
LOG_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(BUDGET_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
