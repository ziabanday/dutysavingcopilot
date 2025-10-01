# tests/search/test_metrics_jsonl_ci.py
import os, json
from pathlib import Path
import pytest

from app.metrics.cb import build_metrics_cb
from app.search.hybrid import hybrid_search  # Phase-3 added metrics hook & hybrid entry

@pytest.mark.offline
def test_metrics_jsonl_emits_when_env_set(tmp_path):
    # Skip if CI didn't request metrics
    metrics_path = os.getenv("METRICS_JSON")
    if not metrics_path:
        pytest.skip("METRICS_JSON not set")

    cb = build_metrics_cb()
    assert cb is not None, "metrics callback should be constructed when METRICS_JSON is set"

    # Use a tiny, offline-safe chunk set; no DB, no network
    chunks = [
        {"chunk_id": "c1", "doc_id": "d1", "content": "piston engine 8407.10 parts"},
        {"chunk_id": "c2", "doc_id": "d2", "content": "small electric motor 8501.10 alternator"},
    ]

    # Trigger at least one event via hybrid_search
    hybrid_search("alternator 8501.10", chunks, k=3, metrics_cb=cb)

    p = Path(metrics_path)
    assert p.exists(), "metrics file should exist"
    # Be lenient: just ensure at least one well-formed line
    with p.open("r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    assert len(lines) >= 1, "should emit at least one metrics event"
    json.loads(lines[-1])  # validates JSONL format
