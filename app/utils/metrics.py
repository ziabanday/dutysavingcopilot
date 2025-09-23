# app/utils/metrics.py
from __future__ import annotations
import csv, json, os, time
from pathlib import Path
from typing import Any, Dict, Iterable, Union

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
