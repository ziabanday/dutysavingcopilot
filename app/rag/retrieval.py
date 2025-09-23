# app/rag/retrieval.py
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# --- get_session import with resilient fallback -----------------------------
try:
    from app.core.db import get_session  # type: ignore
except Exception:
    try:
        from app.core.database import get_session  # type: ignore
    except Exception:
        try:
            from app.db.session import get_session  # type: ignore
        except Exception:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            DB_URL = os.getenv("DATABASE_URL", "sqlite:///local.db")
            connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
            _engine = create_engine(DB_URL, connect_args=connect_args, future=True)
            _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

            @contextmanager
            def get_session() -> Session:
                db = _SessionLocal()
                try:
                    yield db
                finally:
                    db.close()
# ----------------------------------------------------------------------------

from app.db.models import HTSItem, Ruling, RulingChunk, Chunk
from app.core.openai_wrapper import embed as embed_api

__all__ = [
    "bm25_search_hts",
    "hybrid_search_rulings",
    "retrieve_context",
    "build_bm25",
    "build_faiss",
    "retrieve_with_fusion",
]

TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# ---------- helpers: env & clamps ------------------------------------------
def _env_float(name: str, default: float, lo: float | None = None, hi: float | None = None) -> float:
    try:
        v = float(os.getenv(name, str(default)))
    except Exception:
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v

def _env_int(name: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    try:
        v = int(float(os.getenv(name, str(default))))
    except Exception:
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v

def clamp_alpha(a: float) -> float:
    return max(0.0, min(1.0, a))

def _safe_top_k(k: Optional[int], max_cap: int = 50) -> int:
    if k is None:
        return DEFAULT_TOP_K
    try:
        kk = int(k)
    except Exception:
        kk = DEFAULT_TOP_K
    return max(1, min(max_cap, kk))
# ---------------------------------------------------------------------------

# --- Retrieval knobs (env-tunable) ------------------------------------------
BM25_K1 = _env_float("BM25_K1", 1.6, lo=0.5, hi=3.0)
BM25_B = _env_float("BM25_B", 0.7, lo=0.0, hi=1.0)
DEFAULT_TOP_K = _env_int("TOP_K", 6, lo=1, hi=50)
FUSION_ALPHA = clamp_alpha(_env_float("FUSION_ALPHA", 0.65, lo=0.0, hi=1.0))
EMBED_DIM_DEFAULT = _env_int("EMBED_DIM", 1536, lo=64, hi=8192)
# ----------------------------------------------------------------------------

# --- Prompt instructions + helper (existing) --------------------------------
PROMPT_INSTRUCTIONS = """
You are an HTS classification assistant. Read the user query and the provided
context snippets from the HTS. Return a JSON object that matches this schema:

{
  "disclaimer": "...",
  "codes": [
    {
      "code": "NNNN.NN",
      "description": "Short plain-English description",
      "duty_rate": null,
      "rationale": "Why this code fits (1–3 sentences)",
      "confidence": 0.0,
      "evidence": [
        {"source": "HTS", "id": "HTS:NNNN.NN", "url": null}
      ]
    }
  ]
}

Rules:
- Always output VALID JSON only (no extra text).
- ALWAYS include AT LEAST ONE candidate code. If you are uncertain,
  include your single best guess and reflect that with a confidence
  between 0.30 and 0.49.
- Confidence is 0.00–1.00.
- Keep descriptions concise.
- Evidence ids should come from the provided context if possible.
"""

def build_prompt(query: str, ctx_snippets: list[str]) -> list[dict]:
    """Return OpenAI messages with the above instructions + context."""
    context_block = "\n\n".join(f"- {s}" for s in ctx_snippets)
    user_msg = f"""User query:
{query}

Context (HTS excerpts):
{context_block}

Return ONLY the JSON object described in the instructions."""
    return [
        {"role": "system", "content": PROMPT_INSTRUCTIONS.strip()},
        {"role": "user", "content": user_msg},
    ]
# ----------------------------------------------------------------------------


def _tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall((text or "").lower())


def _normalize(scores: List[Tuple[int, float]]) -> Dict[int, float]:
    if not scores:
        return {}
    vals = [s for _, s in scores]
    lo, hi = min(vals), max(vals)
    if math.isclose(hi, lo):
        return {i: 0.0 for i, _ in scores}
    span = hi - lo
    return {i: (s - lo) / span for i, s in scores}


def _cosine(u: np.ndarray, v: np.ndarray, eps: float = 1e-8) -> float:
    num = float(np.dot(u, v))
    den = float(np.linalg.norm(u) * np.linalg.norm(v)) + eps
    return num / den


def embed_query(text: str) -> np.ndarray:
    try:
        vec = embed_api(text=text, model="text-embedding-3-small")
        arr = np.array(vec, dtype=np.float32)
        if arr.ndim != 1:
            arr = arr.reshape(-1).astype(np.float32)
        return arr
    except Exception:
        # Defensive fallback so retrieval never crashes due to embed hiccups
        return np.zeros((EMBED_DIM_DEFAULT,), dtype=np.float32)


@dataclass
class HTSRow:
    code: str
    description: str
    duty_rate: Optional[str]
    chapter: Optional[str]


@dataclass
class RulingChunkRow:
    chunk_id: int
    ruling_id: str
    url: str
    text: str
    embedding: np.ndarray
    bm25_score: float = 0.0
    vec_score: float = 0.0
    hybrid_score: float = 0.0


# =============================== HTS (BM25) =================================
def bm25_search_hts(query: str, top_k: Optional[int] = None) -> List[HTSRow]:
    """BM25 over hts_items.description + notes."""
    k = _safe_top_k(top_k)
    try:
        with get_session() as db:  # type: Session
            rows: List[HTSItem] = db.query(HTSItem).all()
    except SQLAlchemyError as e:
        # Missing table / fresh DB → return empty gracefully
        print(f"[retrieval] HTS query skipped: {e}")
        rows = []

    if not rows:
        return []

    corpus_docs: List[str] = []
    for r in rows:
        notes_txt = ""
        try:
            if isinstance(r.notes, dict):
                notes_txt = " ".join(f"{k}: {v}" for k, v in r.notes.items())
            elif isinstance(r.notes, list):
                notes_txt = " ".join(str(x) for x in r.notes)
            elif r.notes:
                notes_txt = str(r.notes)
        except Exception:
            notes_txt = ""
        corpus_docs.append(f"{r.description or ''} {notes_txt}")

    tokenized_corpus = [_tokenize(doc) for doc in corpus_docs]
    if not tokenized_corpus:
        return []

    bm25 = BM25Okapi(tokenized_corpus, k1=BM25_K1, b=BM25_B)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(enumerate(scores), key=lambda t: (t[1], -t[0]), reverse=True)[:k]

    out: List[HTSRow] = []
    for idx, _ in ranked:
        r = rows[idx]
        out.append(
            HTSRow(
                code=r.code,
                description=r.description or "",
                duty_rate=r.duty_rate,
                chapter=r.chapter,
            )
        )
    return out


# ======================== Rulings (Hybrid BM25+Vec) ==========================
def hybrid_search_rulings(query: str, top_k: Optional[int] = 20, alpha: float = FUSION_ALPHA) -> List[RulingChunkRow]:
    """Hybrid BM25 + vector over ruling_chunks."""
    k = _safe_top_k(top_k)
    a = clamp_alpha(alpha)
    qvec = embed_query(query)

    try:
        with get_session() as db:  # type: Session
            pairs = (
                db.query(RulingChunk)
                .join(Ruling, Ruling.id == RulingChunk.ruling_id_fk)
                .add_entity(Ruling)
                .all()
            )
    except SQLAlchemyError as e:
        print(f"[retrieval] RULING query skipped: {e}")
        pairs = []

    if not pairs:
        return []

    texts = [c.text for c, _ in pairs]
    tokenized = [_tokenize(t or "") for t in texts]
    if not tokenized:
        return []

    bm25 = BM25Okapi(tokenized, k1=BM25_K1, b=BM25_B)
    bm25_norm = _normalize(list(enumerate(bm25.get_scores(_tokenize(query)))))

    vec_pairs: List[Tuple[int, float]] = []
    for idx, (c, _r) in enumerate(pairs):
        try:
            emb = np.array(c.embedding or [], dtype=np.float32)
        except Exception:
            emb = np.zeros((EMBED_DIM_DEFAULT,), dtype=np.float32)

        if emb.ndim != 1:
            emb = emb.reshape(-1).astype(np.float32)

        # pad/truncate to match qvec
        dim = int(qvec.shape[0]) if qvec.size else EMBED_DIM_DEFAULT
        if emb.shape != (dim,):
            fixed = np.zeros((dim,), dtype=np.float32)
            fixed[: min(dim, emb.size)] = emb[: min(dim, emb.size)]
            emb = fixed

        score = 0.0 if qvec.size == 0 else _cosine(qvec, emb)
        vec_pairs.append((idx, score))

    vec_norm = _normalize(vec_pairs)

    rows: List[RulingChunkRow] = []
    for idx, ((c, r)) in enumerate(pairs):
        b = bm25_norm.get(idx, 0.0)
        v = vec_norm.get(idx, 0.0)
        hybrid = a * v + (1 - a) * b
        rows.append(
            RulingChunkRow(
                chunk_id=c.id,
                ruling_id=r.ruling_id,
                url=r.url,
                text=c.text or "",
                embedding=np.array(c.embedding or [], dtype=np.float32),
                bm25_score=b,
                vec_score=v,
                hybrid_score=hybrid,
            )
        )

    rows.sort(key=lambda x: (x.hybrid_score, x.bm25_score, -x.chunk_id), reverse=True)
    return rows[:k]


# ========================= Merge context for prompting =======================
def retrieve_context(query: str, top_hts: int = 8, top_chunks: int = 6) -> Dict[str, Any]:
    """Merge HTS + RULING chunks into a compact RAG context payload."""
    hts = bm25_search_hts(query, top_k=top_hts)
    chunks = hybrid_search_rulings(query, top_k=top_chunks)

    def _excerpt(t: str, n: int = 120) -> str:
        t = (t or "").replace("\n", " ").strip()
        return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"

    ruling_snippets = [
        {
            "id": str(rc.chunk_id),
            "ruling_id": rc.ruling_id,
            "url": rc.url,
            "excerpt": _excerpt(rc.text),
            "hybrid_score": round(rc.hybrid_score, 4),
            "bm25": round(rc.bm25_score, 4),
            "vec": round(rc.vec_score, 4),
        }
        for rc in chunks
    ]

    hts_rows = [
        {
            "code": h.code,
            "description": h.description,
            "duty_rate": h.duty_rate,
            "chapter": h.chapter,
        }
        for h in hts
    ]

    return {
        "hts": hts_rows,
        "rulings": ruling_snippets,
        "meta": {"query": query, "counts": {"hts": len(hts_rows), "rulings": len(ruling_snippets)}},
    }


# =============================================================================
# Week-3 additions: BM25/Vector (chunks table) + fusion retrieval for evidence
# =============================================================================

# Module-level caches for speed (rebuilt by build_bm25 / build_faiss)
_CHUNK_ROWS: List[Chunk] = []
_TOKENIZED_CHUNKS: List[List[str]] = []
_BM25_MODEL: Optional[BM25Okapi] = None
_EMB_MATRIX: Optional[np.ndarray] = None  # shape: (N, D) or None if not built

def _load_chunks(session: Session) -> List[Chunk]:
    try:
        rows: List[Chunk] = session.query(Chunk).all()
    except SQLAlchemyError as e:
        print(f"[retrieval] chunks query failed: {e}")
        rows = []
    return rows

def build_bm25(session: Session) -> bool:
    """
    (Re)build in-memory BM25 index over `chunks.text`.
    Called by: python -m app.rag.reindex --bm25
    """
    global _CHUNK_ROWS, _TOKENIZED_CHUNKS, _BM25_MODEL
    _CHUNK_ROWS = _load_chunks(session)
    _TOKENIZED_CHUNKS = [_tokenize(c.text or "") for c in _CHUNK_ROWS]
    if not _TOKENIZED_CHUNKS:
        _BM25_MODEL = None
        return False
    _BM25_MODEL = BM25Okapi(_TOKENIZED_CHUNKS, k1=BM25_K1, b=BM25_B)
    return True

def build_faiss(session: Session, out_path: str = "data/index/faiss.index") -> bool:
    """
    Dev-friendly vector 'index'. If faiss is unavailable, we persist a plain
    NumPy matrix to disk and use cosine sims at query-time.
    Called by: python -m app.rag.reindex --vectors
    """
    global _CHUNK_ROWS, _EMB_MATRIX
    if not _CHUNK_ROWS:
        _CHUNK_ROWS = _load_chunks(session)

    embs: List[np.ndarray] = []
    dim = None
    for c in _CHUNK_ROWS:
        v = np.array(c.embedding or [], dtype=np.float32)
        if v.ndim != 1:
            v = v.reshape(-1).astype(np.float32)

        if v.size == 0:
            if dim is None:
                dim = EMBED_DIM_DEFAULT
            v = np.zeros((dim,), dtype=np.float32)

        if dim is None:
            dim = int(v.shape[0]) if v.size else EMBED_DIM_DEFAULT

        if v.shape != (dim,):
            vv = np.zeros((dim,), dtype=np.float32)
            vv[: min(dim, v.size)] = v[: min(dim, v.size)]
            v = vv

        embs.append(v)

    _EMB_MATRIX = np.stack(embs, axis=0) if embs else None

    # Persist simple artifact so "reindex" is reproducible
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        if _EMB_MATRIX is not None:
            np.save(out_path + ".npy", _EMB_MATRIX)
        with open(out_path + ".ids", "w", encoding="utf-8") as f:
            for c in _CHUNK_ROWS:
                f.write(f"{c.chunk_id}\t{c.source_id}\n")
    except Exception as e:
        print(f"[retrieval] saving vector artifact failed: {e}")
    return _EMB_MATRIX is not None

def _vector_scores(qvec: np.ndarray) -> List[Tuple[int, float]]:
    """
    Cosine(q, chunk_i) for all i in cache. Returns list of (idx, score).
    """
    if _EMB_MATRIX is None or _EMB_MATRIX.size == 0:
        return []
    denom = (np.linalg.norm(_EMB_MATRIX, axis=1) * (np.linalg.norm(qvec) + 1e-8)) + 1e-8
    sims = (_EMB_MATRIX @ qvec) / denom
    return list(enumerate(sims.tolist()))

# --- BEGIN Week-4 compatibility helpers ---
def _hydrate_hits_with_meta(hits):
    """
    Transform raw hits (chunk_id, text, score...) into API-ready items:
      {code, anchor, snippet, score}
    Uses DB to fetch Chunk.meta (for code) and build stable anchor.
    """
    try:
        from sqlalchemy.orm import Session
        from app.ingest.hts import _resolve_engine
        from app.db.models import Chunk
        e = _resolve_engine(); s = Session(e)
        out = []
        for h in hits or []:
            cid = h.get("chunk_id")
            r = s.query(Chunk).filter_by(chunk_id=cid).first() if cid else None
            meta = (r.meta or {}) if r else {}
            out.append({
                "code": meta.get("code"),
                "anchor": f"{r.source_id}#{r.idx}" if r else (cid or ""),
                "snippet": ((r.text or h.get("text") or "")[:300]) if r else (h.get("text") or "")[:300],
                "score": h.get("score", 0.0),
            })
        return out
    except Exception as e:
        print("[hydrate_hits] error:", e)
        # fallback: at least provide minimal shape
        return [{
            "code": None,
            "anchor": h.get("chunk_id",""),
            "snippet": (h.get("text") or "")[:300],
            "score": h.get("score", 0.0),
        } for h in (hits or [])]
# --- END Week-4 compatibility helpers ---

def retrieve_with_fusion(session: Optional[Session] = None,
                         query: str = "",
                         top_k: int = DEFAULT_TOP_K,
                         alpha: float = FUSION_ALPHA) -> List[Dict[str, Any]]:
    """
    Unified retrieval over the Week-3 `chunks` table.
    - Builds BM25 / embedding caches on demand if missing.
    - Hybrid score = alpha * cosine + (1 - alpha) * bm25_normalized.
    Returns: API-ready items [{code, anchor, snippet, score}] (hydrated).

    Session is OPTIONAL; if not provided, one will be created and closed here.
    """
    global _BM25_MODEL

    # Create/own session if not provided
    created = False
    if session is None:
        try:
            from app.ingest.hts import _resolve_engine
            from sqlalchemy.orm import Session as _Sess
            session = _Sess(_resolve_engine())
            created = True
        except Exception as e:
            print("[retrieve_with_fusion] could not create DB session:", e)
            return []

    try:
        k = _safe_top_k(top_k)
        a = clamp_alpha(alpha)

        # Ensure caches
        if _BM25_MODEL is None or not _CHUNK_ROWS:
            build_bm25(session)
        if _EMB_MATRIX is None:
            build_faiss(session)

        if not _CHUNK_ROWS:
            return []

        # BM25
        bm25_scores: List[Tuple[int, float]] = []
        if _BM25_MODEL is not None:
            bm25_scores = list(enumerate(_BM25_MODEL.get_scores(_tokenize(query))))
        bm25_norm = _normalize(bm25_scores)

        # Vectors
        qvec = embed_query(query)
        vec_scores = _vector_scores(qvec)
        vec_norm = _normalize(vec_scores)

        # Combine
        fused: List[Tuple[int, float, float, float]] = []
        for idx in range(len(_CHUNK_ROWS)):
            b = bm25_norm.get(idx, 0.0)
            v = vec_norm.get(idx, 0.0)
            fused.append((idx, a * v + (1 - a) * b, b, v))

        fused.sort(key=lambda t: (t[1], t[2], -t[0]), reverse=True)
        fused = fused[: max(1, k)]

        raw: List[Dict[str, Any]] = []
        for idx, score, b, v in fused:
            c = _CHUNK_ROWS[idx]
            raw.append({
                "chunk_id": c.chunk_id,
                "source_id": c.source_id,
                "text": c.text or "",
                "score": float(score),
                "bm25": float(b),
                "vec": float(v),
            })

        # Hydrate into API-ready evidence items {code, anchor, snippet, score}
        return _hydrate_hits_with_meta(raw)
    finally:
        if created:
            try:
                session.close()
            except Exception:
                pass
