# app/api/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.classify import router as classify_router

app = FastAPI(
    title="Duty Saving Copilot",
    version="0.2.1",
    description="Small FastAPI app that classifies queries into HTS codes with strict JSON guardrails.",
)

# Open CORS for local testing; tighten in prod if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

# REST routes
app.include_router(classify_router)
