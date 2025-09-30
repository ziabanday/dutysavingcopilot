# app/metrics/cb.py
from __future__ import annotations
from pathlib import Path
import json, os, time
from typing import Callable, Optional, Dict, Any

def build_metrics_cb() -> Optional[Callable[[str, Dict[str, Any]], None]]:
    out = os.getenv("METRICS_JSON")
    if not out:
        return None
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _cb(event: str, payload: Dict[str, Any]) -> None:
        rec = {"ts": time.time(), "event": event}
        try:
            if payload:
                rec.update(payload)
        except Exception:
            pass
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return _cb
