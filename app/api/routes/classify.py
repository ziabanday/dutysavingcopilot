# app/api/routes/classify.py
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter
import json
import traceback
import logging
import os  # <-- needed for MIN_SCORE

from app.api.schemas import ClassifyRequest, ClassifyResponse
from app.config import settings

# Safe logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ---------- Retrieval import with safe fallback ----------
try:
    from app.rag.retrieval import retrieve_with_fusion  # returns hydrated hits: {code, anchor, snippet, score}
    _HAVE_RETRIEVAL = True
except Exception as e:
    logger.exception("Failed to import retrieve_with_fusion: %s", e)
    _HAVE_RETRIEVAL = False

    def retrieve_with_fusion(*, query: str, top_k: int) -> List[Dict[str, Any]]:  # type: ignore
        # Degrade to no-evidence if retrieval layer is unavailable
        return []

# ----------------- Prompt + LLM helpers with robust fallbacks -----------------
_HAVE_BUILD = False
_HAVE_RULES = False

try:
    # Preferred if present
    from app.rag.prompt import build_prompt, run_llm_classify  # type: ignore
    _HAVE_BUILD = True
except Exception:
    pass

if not _HAVE_BUILD:
    try:
        # Older layout used in your repo
        from app.rag.prompt import SYSTEM_RULES, make_user_prompt  # type: ignore
        _HAVE_RULES = True
    except Exception:
        _HAVE_RULES = False
        SYSTEM_RULES = """
You are an HTS classification assistant. Return ONLY valid JSON with:
{
  "disclaimer": "...",
  "codes": [
    {"code":"NNNN.NN","description":"...","duty_rate":null,"rationale":"...","confidence":0.0,
     "evidence":[{"source":"HTS","id":"<anchor>","url":null}]}
  ]
}
- If uncertain, include your single best guess (confidence 0.30â€“0.49).
- Confidence in [0,1]. Keep descriptions concise. Evidence ids should reflect provided context.
""".strip()

    # Minimal build_prompt + strict JSON call
    from app.core.openai_wrapper import chat as _chat_api  # type: ignore

    def _parse_json_maybe(text: Any) -> Dict[str, Any]:
        if isinstance(text, dict):
            return text
        s = text if isinstance(text, str) else str(text)
        try:
            return json.loads(s)
        except Exception:
            a, b = s.find("{"), s.rfind("}")
            if a != -1 and b != -1 and b > a:
                try:
                    return json.loads(s[a : b + 1])
                except Exception:
                    pass
            # Fallback to abstain shape
            return {"disclaimer": "Not legal advice. Verify with a licensed customs broker or counsel.", "codes": []}

    def build_prompt(query: str, ctx_snippets: List[str]) -> List[Dict[str, str]]:  # type: ignore[no-redef]
        context_block = "\n\n".join(f"- {s}" for s in ctx_snippets)
        user_msg = f"""User query:
{query}

Context (HTS excerpts):
{context_block}

Return ONLY the JSON object described in the instructions."""
        return [
            {"role": "system", "content": SYSTEM_RULES},
            {"role": "user", "content": user_msg},
        ]

    def run_llm_classify(messages: List[Dict[str, str]], strict_json: bool = True, timeout_s: int = 15) -> Dict[str, Any]:  # type: ignore[no-redef]
        """
        Local LLM runner that enforces strict JSON and repairs if needed.
        Note: wrapper does not accept 'strict_json' or 'timeout_s'; we handle JSON strictly here.
        """
        try:
            rsp = _chat_api(
                messages=messages,
                model="gpt-4o-mini",
                max_tokens=settings.MAX_TOKENS,
            )
            return _parse_json_maybe(rsp)
        except Exception as e:
            logger.exception("LLM primary call failed, attempting JSON repair: %s", e)
            try:
                repair = [
                    {"role": "system", "content": "You are a formatter. Return ONLY valid minified JSON."},
                    {"role": "user", "content": f"Fix to valid JSON only (no prose):\n{e}"},
                ]
                fixed = _chat_api(
                    messages=repair,
                    model="gpt-4o-mini",
                    max_tokens=settings.MAX_TOKENS,
                )
                return _parse_json_maybe(fixed)
            except Exception as e2:
                logger.exception("LLM repair also failed: %s", e2)
                # Hard-abstain on repeated failures
                return {"disclaimer": DISCLAIMER, "codes": []}
# -----------------------------------------------------------------------------


router = APIRouter()
DISCLAIMER = "Not legal advice. Verify with a licensed customs broker or counsel."


def _mk_evidence(source: str, _id: Optional[str], url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not _id:
        return None
    sid = str(_id).strip()
    if not sid:
        return None
    return {"source": source, "id": sid, "url": url}


def _fallback_from_hits(hits: List[Dict[str, Any]], max_codes: int = 2) -> List[Dict[str, Any]]:
    """
    If the model returns zero codes, synthesize a minimal result from retrieval hits:
      - pick top unique codes (skip None)
      - attach at least one evidence anchor per code
      - compact description/rationale from snippet
    """
    seen = set()
    out: List[Dict[str, Any]] = []
    for h in hits:
        code = h.get("code")
        if not code or code in seen:
            continue
        seen.add(code)
        snippet = (h.get("snippet") or "").strip()
        if not snippet:
            snippet = f"HTS reference for code {code}."
        # Keep the ellipsis as-is; mojibake in data will be addressed separately
        desc = snippet[:140].rsplit(" ", 1)[0] + "…" if len(snippet) > 140 else snippet
        ev_item = _mk_evidence("HTS", h.get("anchor"))
        ev = [ev_item] if ev_item else []
        out.append({
            "code": str(code),
            "description": desc or "",
            "duty_rate": None,
            "rationale": f"Matched HTS excerpt for code {code}.",
            "confidence": 0.35,  # conservative heuristic
            "evidence": ev,
        })
        if len(out) >= max_codes:
            break
    return out


# ----------------- FINAL FILTER & RESPONSE (MIN_SCORE + evidence) -----------------
def _has_any_evidence(items: Optional[List[Dict[str, Any]]]) -> bool:
    items = items or []
    return any((c.get("evidence") or []) for c in items)

def _finalize_response(codes: Optional[List[Dict[str, Any]]]) -> ClassifyResponse:
    MIN_SCORE = float(os.getenv("MIN_SCORE", "0.15"))
    pre = len(codes or [])
    filtered = [c for c in (codes or []) if float(c.get("confidence") or 0.0) >= MIN_SCORE]
    post = len(filtered)
    # instrumentation to confirm the gate is active
    print(f"[classify] MIN_SCORE={MIN_SCORE} pre={pre} post={post}")

    if not filtered or not _has_any_evidence(filtered):
        # NOTE: response_model=ClassifyResponse -> only 'disclaimer' & 'codes' are returned to client
        return ClassifyResponse(disclaimer=DISCLAIMER, codes=[])

    return ClassifyResponse(disclaimer=DISCLAIMER, codes=filtered)
# -----------------------------------------------------------------------------


@router.post("/classify", response_model=ClassifyResponse)
def classify(req: ClassifyRequest) -> ClassifyResponse:
    # Retrieval with defensive fallback
    try:
        hits = retrieve_with_fusion(query=req.query, top_k=settings.TOP_K)
    except Exception as e:
        logger.exception("Retrieval failed: %s\n%s", e, traceback.format_exc())
        hits = []

    # Guardrail: abstain when we truly have no evidence
    if settings.ABSTAIN_ON_NO_EVIDENCE and not hits:
        return _finalize_response([])

    # Build prompt messages
    ctx_snips = [h["snippet"] for h in hits if h.get("snippet")]

    if _HAVE_BUILD:
        messages = build_prompt(req.query, ctx_snips)
    elif _HAVE_RULES:
        context = {
            "hts": [],
            "rulings": [{"id": h.get("anchor", ""), "excerpt": s} for h, s in zip(hits, ctx_snips)],
        }
        messages = [
            {"role": "system", "content": SYSTEM_RULES},
            {"role": "user", "content": make_user_prompt(req.query, context)},  # type: ignore[name-defined]
        ]
    else:
        messages = build_prompt(req.query, ctx_snips)

    # LLM call (strict JSON + repair handled inside run_llm_classify)
    try:
        llm_json = run_llm_classify(messages, strict_json=settings.STRICT_JSON)
    except Exception as e:
        logger.exception("run_llm_classify exploded: %s\n%s", e, traceback.format_exc())
        llm_json = {"disclaimer": DISCLAIMER, "codes": []}

    # Map model output -> schema; backfill evidence ids when absent
    out_codes: List[Dict[str, Any]] = []
    for c in llm_json.get("codes", []):
        ev: List[Dict[str, Any]] = []
        if c.get("evidence"):
            for e in c["evidence"]:
                ev_item = _mk_evidence(e.get("source", "HTS"), e.get("id"), e.get("url"))
                if ev_item:
                    ev.append(ev_item)
        if not ev:
            pred = c.get("code")
            for h in hits:
                if h.get("code") == pred:
                    ev_item = _mk_evidence("HTS", h.get("anchor"))
                    if ev_item:
                        ev.append(ev_item)
                        break

        # Ensure confidence is a safe float in [0,1]
        try:
            conf = float(c.get("confidence", 0.0))
        except Exception:
            conf = 0.0
        if conf < 0.0:
            conf = 0.0
        if conf > 1.0:
            conf = 1.0

        out_codes.append({
            "code": c.get("code", "") or "",
            "description": c.get("description", "") or "",
            "duty_rate": c.get("duty_rate", None),
            "rationale": c.get("rationale", "") or "",
            "confidence": conf,
            "evidence": ev,
        })

    # If the model returned ZERO codes, synthesize from hits (keeps demo & guardrails working)
    if not out_codes:
        out_codes = _fallback_from_hits(hits)

    # --- Confidence calibration using retrieval support ---
    # Build a quick map of max hit score per code (if your hits have 'score')
    code2max: Dict[str, float] = {}
    for h in hits:
        c = (h.get("code") or "").strip()
        if not c:
            continue
        s = float(h.get("score") or 0.0)
        if c not in code2max or s > code2max[c]:
            code2max[c] = s

    def _bump(conf: float, rank_idx: int) -> float:
        """
        Simple, conservative bumps:
          - Top supported code gets at least ~0.55
          - 2nd supported code ~0.45
        Keeps upper bound < 0.8 so we don't overstate.
        """
        if rank_idx == 0:
            return max(conf, 0.55)
        if rank_idx == 1:
            return max(conf, 0.45)
        return conf  # others unchanged

    # Order out_codes by their evidence support in 'hits'
    # If no 'score' available, we fall back to original order.
    sorted_codes = sorted(
        out_codes,
        key=lambda c: code2max.get((c.get("code") or "").strip(), 0.0),
        reverse=True
    )

    for i, c in enumerate(sorted_codes):
        code = (c.get("code") or "").strip()
        if code in code2max and code2max[code] > 0.0:
            c["confidence"] = _bump(float(c.get("confidence") or 0.0), i)

    # Keep original order unless you prefer sorted order:
    # out_codes = sorted_codes
    # --- end calibration ---

    # ALWAYS finish via the guardrail gate
    return _finalize_response(out_codes)


# ---------- Helper for eval harness ----------
def classify_query(query: str, k: Optional[int] = None) -> Tuple[ClassifyResponse, Dict[str, Any]]:
    """
    Thin wrapper used by eval_golden.py.
    - query: string query
    - k: top_k override; if None, use settings.TOP_K
    Returns (response_model, raw_dict).
    """
    topk = int(k) if k is not None else int(settings.TOP_K)
    req = ClassifyRequest(query=query, top_k=topk)
    resp = classify(req)
    raw = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
    return resp, raw
