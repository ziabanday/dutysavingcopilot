from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from ..core.settings import CORS_ORIGINS, DISLCAIMER_TEXT
from ..utils.logging_setup import get_logger

log = get_logger("api")

app = FastAPI(title="HTS Duty-Saving Copilot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory rate limiter: 10 req/min per ip
from time import time
from collections import defaultdict, deque
_window = 60.0
_max_req = 10
_buckets = defaultdict(lambda: deque())

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    now = time()
    q = _buckets[ip]
    while q and now - q[0] > _window:
        q.popleft()
    if len(q) >= _max_req:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    q.append(now)
    return await call_next(request)

class Evidence(BaseModel):
    source: str
    id: str
    url: Optional[str] = None

class CodeCandidate(BaseModel):
    code: str = Field(..., pattern=r"^\d{4}\.\d{2}(?:\.\d{2})?$")
    description: str
    duty_rate: Optional[str] = None
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[Evidence]

class ClassifyResponse(BaseModel):
    disclaimer: str
    codes: List[CodeCandidate]

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/classify", response_model=ClassifyResponse)
async def classify_stub(body: dict):
    # Stub to satisfy contract; real RAG logic wired in Week-2/3
    log.info("classify_stub called (input redacted)")
    example = ClassifyResponse(
        disclaimer=DISLCAIMER_TEXT,
        codes=[
            CodeCandidate(
                code="3926.90.99",
                description="Other articles of plastics",
                duty_rate="5%",
                rationale="Placeholder reasoning; retrieval + rulings will be attached in later milestone.",
                confidence=0.25,
                evidence=[
                    Evidence(source="HTS", id="HTS:3926.90", url=None)
                ]
            )
        ]
    )
    return example
