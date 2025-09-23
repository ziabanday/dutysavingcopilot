# tests/test_classify_schema.py
from __future__ import annotations
import json
import os
from fastapi.testclient import TestClient

os.environ["NO_API"] = "1"  # ensure wrapper runs in stub mode for CI

from app.api.main import app  # noqa: E402
from app.rag import retrieval as retrieval_mod  # noqa: E402

client = TestClient(app)


def fake_retrieve_context(query: str):
    return {
        "hts": [
            {"code": "8504.40", "description": "Power supplies; static converters", "duty_rate": "3%", "chapter": "85"}
        ],
        "rulings": [
            {"id": "101", "ruling_id": "NY123456", "url": "https://rulings.cbp.gov/NY123456",
             "excerpt": "Classification of AC/DC adapter...", "hybrid_score": 0.8, "bm25": 0.7, "vec": 0.9}
        ],
        "meta": {"query": query, "counts": {"hts": 1, "rulings": 1}},
    }


def test_classify_returns_valid_json(monkeypatch):
    monkeypatch.setattr(retrieval_mod, "retrieve_context", fake_retrieve_context)

    body = {"query": "AC/DC power adapter 12V 2A"}
    r = client.post("/classify", json=body)
    assert r.status_code == 200

    data = r.json()
    # basic schema assertions
    assert "disclaimer" in data and isinstance(data["disclaimer"], str)
    assert "codes" in data and isinstance(data["codes"], list)
    assert len(data["codes"]) >= 1

    cand = data["codes"][0]
    assert "code" in cand and isinstance(cand["code"], str)
    assert "description" in cand and isinstance(cand["description"], str)
    assert "confidence" in cand and 0.0 <= float(cand["confidence"]) <= 1.0
    assert "evidence" in cand and isinstance(cand["evidence"], list)
