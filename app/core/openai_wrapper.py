from __future__ import annotations
import time
from typing import List, Dict, Any
from openai import OpenAI
from .settings import OPENAI_API_KEY, OPENAI_CHAT_MODEL, OPENAI_EMBED_MODEL
from app.utils.budget import add_and_check
from app.utils.logging_setup import get_logger

client = OpenAI(api_key=OPENAI_API_KEY)
log = get_logger("openai")

class BudgetExceeded(Exception):
    pass

def chat(messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=messages,
        **kwargs
    )
    dt = (time.perf_counter() - t0) * 1000.0
    usage = resp.usage or None
    in_toks = getattr(usage, "prompt_tokens", 0) if usage else 0
    out_toks = getattr(usage, "completion_tokens", 0) if usage else 0
    used, limit, allowed = add_and_check(in_toks + out_toks)
    log.info(f"chat_completion | model={OPENAI_CHAT_MODEL} | tokens_in={in_toks} | tokens_out={out_toks} | latency_ms={dt:.0f} | budget_used={used}/{limit}")
    if not allowed:
        raise BudgetExceeded("Monthly token budget exceeded")
    return {"response": resp, "latency_ms": dt, "tokens_in": in_toks, "tokens_out": out_toks}

def embed(texts: List[str], **kwargs) -> Dict[str, Any]:
    t0 = time.perf_counter()
    resp = client.embeddings.create(model=OPENAI_EMBED_MODEL, input=texts, **kwargs)
    dt = (time.perf_counter() - t0) * 1000.0
    # OpenAI embeddings API does not always return usage tokens; conservatively count 1 token per 4 characters
    approx_tokens = sum(len(t)//4+1 for t in texts)
    used, limit, allowed = add_and_check(approx_tokens)
    log.info(f"embeddings | model={OPENAI_EMBED_MODEL} | approx_tokens={approx_tokens} | latency_ms={dt:.0f} | budget_used={used}/{limit}")
    if not allowed:
        raise BudgetExceeded("Monthly token budget exceeded")
    return {"response": resp, "latency_ms": dt, "approx_tokens": approx_tokens}
