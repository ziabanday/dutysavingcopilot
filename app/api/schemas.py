# app/api/schemas.py
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, AnyUrl, ConfigDict


class Evidence(BaseModel):
    """Provenance for a candidate code decision."""
    model_config = ConfigDict(extra="forbid")

    # Source must be either HTS (Tariff schedule) or RULING (CBP ruling)
    source: Literal["HTS", "RULING"]
    id: str = Field(..., description="Stable identifier, e.g., 'HTS:8504.40' or 'HQ H301619#12'")
    url: Optional[AnyUrl | str] = Field(
        default=None,
        description="Public URL for rulings when available; null for HTS rows without URLs.",
    )


class CodeCandidate(BaseModel):
    """One candidate HS/HTS code with rationale and provenance."""
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        pattern=r"^\d{4}\.\d{2}(?:\.\d{2})?$",
        description="Formatted as NNNN.NN or NNNN.NN.NN",
    )
    description: str
    duty_rate: Optional[str] = None
    rationale: str = Field(..., description="1–3 sentences. No boilerplate.")
    confidence: float = Field(..., ge=0.0, le=1.0)
    # We prefer at least one item, but keep it optional so the server can inject fallback evidence.
    evidence: List[Evidence] = Field(default_factory=list)


class ClassifyResponse(BaseModel):
    """Top candidate codes for a query."""
    model_config = ConfigDict(extra="forbid")

    disclaimer: str
    codes: List[CodeCandidate]


class ClassifyRequest(BaseModel):
    """Incoming classification request."""
    model_config = ConfigDict(extra="forbid")

    query: str
    # Optional so you can probe different K values during eval/QA; route may clamp/ignore.
    top_k: Optional[int] = Field(default=None, ge=1, le=10)
