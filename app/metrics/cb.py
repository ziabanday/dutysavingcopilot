# app/metrics/cb.py
from __future__ import annotations
from pathlib import Path
import json, os, time
from typing import Callable, Optional, Dict, Any

def build_metrics_cb() -> Optional[Callable[..., None]]:
    out = os.getenv("METRICS_JSON")
    if not out:
        return None
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _cb(*args, **kwargs) -> None:
        """
        Flexible adapter:
          - _cb(event: str, payload: dict)
          - _cb(payload: dict)
          - _cb(event="...", payload={...})
          - _cb(**payload)  (last resort; event defaults to 'event')
        """
        event = "event"
        payload: Dict[str, Any] = {}

        # Positional forms
        if len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], dict):
            event, payload = args[0], args[1]
        elif len(args) == 1 and isinstance(args[0], dict):
            payload = args[0]
        else:
            # Keyword forms
            if "event" in kwargs or "payload" in kwargs:
                event = kwargs.get("event", event)
                payload = kwargs.get("payload", payload)
            elif kwargs:
                # Treat arbitrary kwargs as payload
                payload = dict(kwargs)

        rec = {"ts": time.time(), "event": event}
        if isinstance(payload, dict):
            try:
                if payload:
                    rec.update(payload)
            except Exception:
                pass
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return _cb
