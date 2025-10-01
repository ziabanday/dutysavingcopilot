# app/utils/metrics.py
from __future__ import annotations
import csv, json, os, time
from pathlib import Path
from typing import Any, Dict, Iterable, Union, Optional

# New superset header (append-only design; rightmost are optional)
_TARGET_HEADER = [
    "ts", "query", "decision", "max_score", "lat_ms",
    "model", "tok_in", "tok_out", "node_lat_ms"
]

def _read_existing_header(path: str) -> Optional[list]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            row = next(reader)
            return row
        except StopIteration:
            return None

def _open_writer(path: str, header: list):
    # Ensure parent directory
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # If file empty/missing → write our superset header once
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    f = open(path, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=header)
    if write_header:
        w.writeheader()
    return f, w


def _append_csv(path: Path, header: Iterable[str], row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(header))
        if not file_exists:
            w.writeheader()
        w.writerow(row)

# ---- OpenAI event log (called by openai_wrapper) ----
_OAI_PATH = Path(os.getenv("OPENAI_EVENTS_CSV", "logs/openai_events.csv"))
_OAI_HEADER = [
    "ts", "event", "model", "tokens_in", "tokens_out", "lat_ms"
]

def log_openai_event(event: str, meta: Dict[str, Any]) -> None:
    try:
        row = {
            "ts": int(time.time()),
            "event": event,
            "model": meta.get("model"),
            "tokens_in": meta.get("tokens_in", 0),
            "tokens_out": meta.get("tokens_out", 0),
            "lat_ms": meta.get("lat_ms", 0),
        }
        _append_csv(_OAI_PATH, _OAI_HEADER, row)
    except Exception:
        # Never let logging break the app
        pass

# ---- /classify call log (called from the route) ----
_CLASSIFY_PATH = Path(os.getenv("CLASSIFY_CSV", "logs/classify_calls.csv"))
_CLASSIFY_HEADER = [
    "ts", "query", "first_code", "first_confidence", "codes_json"
]

def log_classify_call(query: str, codes: Iterable[Dict[str, Any] | Any]) -> None:
    """
    `codes` can be a list of dicts or Pydantic models; we handle both.
    """
    try:
        codes_py = []
        for c in codes or []:
            # Pydantic model -> dict
            if hasattr(c, "model_dump"):
                codes_py.append(c.model_dump())
            elif hasattr(c, "dict"):
                codes_py.append(c.dict())
            else:
                codes_py.append(dict(c)) if isinstance(c, dict) else codes_py.append({})
        first = codes_py[0] if codes_py else {}
        row = {
            "ts": int(time.time()),
            "query": query,
            "first_code": first.get("code"),
            "first_confidence": first.get("confidence"),
            "codes_json": json.dumps(codes_py, ensure_ascii=False),
        }
        _append_csv(_CLASSIFY_PATH, _CLASSIFY_HEADER, row)
    except Exception:
        pass

# ---- Week-3: evaluation CSV (golden-set runner writes here) -----------------

def append_eval_row(path: Union[str, Path], row: Dict[str, Any]) -> None:
    """
    Append a single evaluation record (adds header on first write).
    Header is derived from the row's keys so you can evolve fields
    (e.g., add 'evidence_covered') without touching this helper.
    """
    try:
        if not row:
            return
        p = Path(path)
        header = sorted(row.keys())
        _append_csv(p, header, row)
    except Exception:
        # Fail-open: eval should never crash on metrics I/O
        pass


# ---- Week-5b Phase-2→4: agent run metrics (back-compatible enrichment) ------

# Legacy constants (kept for reference/back-compat; function below now accepts `path`)
_AGENT_METRICS_PATH = Path(os.getenv("METRICS_PATH", "data/metrics/eval.csv"))
_AGENT_METRICS_HEADER = ["ts", "query", "decision", "max_score", "lat_ms"]

def append_agent_metrics(
    query: str,
    decision: str,
    max_score: float,
    lat_ms: float,
    path: str = "data/metrics/eval.csv",
    *,
    model: Optional[str] = None,
    tok_in: Optional[int] = None,
    tok_out: Optional[int] = None,
    node_lat_ms: Optional[Dict[str, Any]] = None,
):
    """
    Append agent metrics with optional enrichment. Back-compatible:
    - If the existing CSV has the *old* header, we only write the old columns.
    - If empty/missing, we create the superset header and write all columns.
    Never throws.
    """
    try:
        existing = _read_existing_header(path)
        if existing is None:
            # Fresh file → create with superset header
            header = _TARGET_HEADER
        else:
            # Respect existing header exactly (no rewrites of old files)
            header = existing

        f, writer = _open_writer(path, header)
        try:
            row = {
                "ts": int(time.time() * 1000),
                "query": query,
                "decision": decision,
                "max_score": f"{(max_score if max_score is not None else 0.0):.6f}",
                "lat_ms": f"{(lat_ms if lat_ms is not None else 0.0):.2f}",
                # Optional enrichments (may be absent if header is old)
                "model": model or "",
                "tok_in": "" if tok_in is None else int(tok_in),
                "tok_out": "" if tok_out is None else int(tok_out),
                "node_lat_ms": (
                    "" if node_lat_ms is None else json.dumps(node_lat_ms, separators=(",", ":"))
                ),
            }
            # Only write keys present in the *actual* header
            writer.writerow({k: row.get(k, "") for k in header})
        finally:
            f.close()
    except Exception:
        # Fail-open: metrics must never crash app/tests
        pass
