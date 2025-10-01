# app/core/openai_wrapper.py
# Real OpenAI calls with a deterministic stub path when NO_API is truthy.
# Now uses a lazy, mockable client so tests/CI can run with zero secrets.

from __future__ import annotations

import os
import time
from typing import Dict, List, Any
from functools import lru_cache

from dotenv import load_dotenv
load_dotenv()  # loads .env from project root (and parents)

# ---- OpenAI client (lazy, mockable singleton) --------------------------------
from openai import OpenAI

# Lazy, mockable singleton. Avoids requiring OPENAI_API_KEY at import time.
_CLIENT = None

def _get_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    # Allow tests/CI to run offline without secrets.
    if os.getenv("OPENAI_API_MOCK") == "1":
        class _DummyClient:
            def __getattr__(self, _):
                raise RuntimeError("OpenAI client is disabled (OPENAI_API_MOCK=1).")
        _CLIENT = _DummyClient()
        return _CLIENT
    # Normal path (prod/local dev). OpenAI() reads OPENAI_API_KEY from env if present.
    _CLIENT = OpenAI()
    return _CLIENT
# -----------------------------------------------------------------------------


# ---- stub-mode helpers ------------------------------------------------------
def _truthy(x) -> bool:
    return str(x).strip().lower() in {"1", "true", "yes", "on"}

def is_stub_mode() -> bool:
    # only stub when NO_API is explicitly truthy (e.g., 1/true/yes/on)
    # (kept for backward-compat with existing env and tests)
    return _truthy(os.getenv("NO_API", "0"))
# -----------------------------------------------------------------------------


def _log(event: str, meta: Dict[str, Any]):
    """
    Minimal logger: ONLY log tokens/latency/metadata — never raw prompts or PII.
    Also tee to a CSV via app.utils.metrics (best-effort; failures are ignored).
    """
    print(f"[openai_wrapper] {event} :: {meta}")
    try:
        from app.utils.metrics import log_openai_event
        log_openai_event(event, meta)
    except Exception:
        pass


# ---- Embeddings with LRU cache ----------------------------------------------
@lru_cache(maxsize=256)
def _embed_cached(text: str, model: str) -> tuple:
    """Call OpenAI once per (text, model) pair; cache the vector."""
    client = _get_client()
    resp = client.embeddings.create(model=model, input=text)
    vec = resp.data[0].embedding
    return (model, tuple(vec))  # tuples so they’re hashable

def embed(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """
    Return an embedding vector (list[float]) and log tokens + latency.

    Dev mode:
      If NO_API is truthy, returns a deterministic pseudo-embedding (stable).

    Prod mode:
      Uses the OpenAI Embeddings API via a lazy singleton with an LRU cache.
    """
    t0 = time.perf_counter()

    # ---- Stub path (dev / CI) ------------------------------------------------
    if is_stub_mode():
        import numpy as np
        seed = abs(hash((model, text))) % (2**32)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(1536).astype("float32").tolist()
        tk_in, tk_out = len(text.split()), 0
        lat_ms = int((time.perf_counter() - t0) * 1000)
        _log("embed", {"model": model, "tokens_in": tk_in, "tokens_out": tk_out, "lat_ms": lat_ms})
        return vec
    # -------------------------------------------------------------------------

    # ---- Real API call (cached) ---------------------------------------------
    _, vec_t = _embed_cached(text, model)
    vec = list(vec_t)
    tk_in, tk_out = len(text.split()), 0  # usage is not exposed via cache; approximate
    lat_ms = int((time.perf_counter() - t0) * 1000)
    _log("embed", {"model": model, "tokens_in": tk_in, "tokens_out": tk_out, "lat_ms": lat_ms})
    return vec
    # -------------------------------------------------------------------------


def chat(
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 400,
    temperature: float = 0.0,
    response_format: Any | None = None,
) -> Dict[str, Any]:
    """
    Create a chat completion and log tokens + latency.

    Returns:
      {"content": str, "tokens_in": int, "tokens_out": int, "lat_ms": int}

    Dev mode:
      If NO_API is truthy, returns a deterministic JSON-shaped string.

    Prod mode:
      Uses the OpenAI Chat Completions API via the lazy singleton client.
    """
    t0 = time.perf_counter()

    # ---- Stub path (dev / CI) ------------------------------------------------
    if is_stub_mode():
        content = (
            '{"disclaimer":"Not legal advice. Verify with a licensed customs broker or counsel.",'
            '"codes":[{"code":"9999.99","description":"Placeholder","duty_rate":null,'
            '"rationale":"Dev mode.","confidence":0.5,'
            '"evidence":[{"source":"HTS","id":"HTS:9999.99","url":null}]}]}'
        )
        tk_in = sum(len(m.get("content", "").split()) for m in messages)
        tk_out = len(content.split())
        lat_ms = int((time.perf_counter() - t0) * 1000)
        _log("chat", {"model": model, "tokens_in": tk_in, "tokens_out": tk_out, "lat_ms": lat_ms})
        return {"content": content, "tokens_in": tk_in, "tokens_out": tk_out, "lat_ms": lat_ms}
    # -------------------------------------------------------------------------

    # ---- Real API call (shared client) --------------------------------------
    client = _get_client()
    try:
        kwargs = dict(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format is not None:
            kwargs["response_format"] = response_format  # e.g., {"type": "json_object"}

        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        tk_in = getattr(usage, "prompt_tokens", 0) if usage else 0
        tk_out = getattr(usage, "completion_tokens", 0) if usage else 0
    except Exception as e:
        raise RuntimeError(f"OpenAI chat call failed: {e}") from e

    lat_ms = int((time.perf_counter() - t0) * 1000)
    _log("chat", {"model": model, "tokens_in": tk_in, "tokens_out": tk_out, "lat_ms": lat_ms})
    return {"content": content, "tokens_in": tk_in, "tokens_out": tk_out, "lat_ms": lat_ms}
    # -------------------------------------------------------------------------


def warmup():
    """Optional: touch the API once in environments where a key is present."""
    try:
        client = _get_client()
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "ok"}],
            max_tokens=1,
            temperature=0.0,
        )
        print("[openai_wrapper] warmup: ok")
    except Exception as e:
        print(f"[openai_wrapper] warmup skipped: {e}")
