from __future__ import annotations
import json, os, datetime, threading
from app.core.settings import BUDGET_DIR, MAX_MONTHLY_TOKENS

_LOCK = threading.Lock()
BUDGET_FILE = os.path.join(BUDGET_DIR, "token_budget.json")

def _month_key(dt: datetime.datetime | None = None) -> str:
    dt = dt or datetime.datetime.utcnow()
    return dt.strftime("%Y-%m")

def _read_state():
    if not os.path.exists(BUDGET_FILE):
        return {"month": _month_key(), "used_tokens": 0}
    try:
        with open(BUDGET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"month": _month_key(), "used_tokens": 0}

def _write_state(state):
    with open(BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def add_and_check(tokens: int) -> tuple[int, int, bool]:
    "Returns (used, limit, allowed) after adding tokens."
    with _LOCK:
        st = _read_state()
        mk = _month_key()
        if st.get("month") != mk:
            st = {"month": mk, "used_tokens": 0}
        st["used_tokens"] += int(tokens)
        allowed = st["used_tokens"] <= MAX_MONTHLY_TOKENS
        _write_state(st)
        return st["used_tokens"], MAX_MONTHLY_TOKENS, allowed

def used_tokens() -> int:
    return _read_state().get("used_tokens", 0)
