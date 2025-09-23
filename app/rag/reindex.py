# app/rag/reindex.py
import argparse
import os
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.db.models import IndexMeta
from app.rag.retrieval import build_bm25, build_faiss

def _resolve_engine():
    """
    Prefer the project's get_engine() if present; otherwise create one
    from DATABASE_URL (default sqlite:///local.db). This avoids import errors
    across slightly different Week-1 scaffolds.
    """
    try:
        from app.db.session import get_engine as _get_engine  # type: ignore
        return _get_engine()
    except Exception:
        db_url = os.getenv("DATABASE_URL", "sqlite:///local.db")
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        return create_engine(db_url, connect_args=connect_args, future=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bm25", action="store_true")
    ap.add_argument("--vectors", action="store_true")
    args = ap.parse_args()

    engine = _resolve_engine()
    with Session(engine) as s:
        if args.bm25:
            ok = build_bm25(s)
            s.add(
                IndexMeta(
                    name="bm25",
                    version=os.getenv("BM25_VERSION", "dev"),
                    details={"k1": os.getenv("BM25_K1"), "b": os.getenv("BM25_B"), "ok": ok},
                )
            )
        if args.vectors:
            ok = build_faiss(s, out_path="data/index/faiss.index")
            s.add(
                IndexMeta(
                    name="faiss",
                    version=os.getenv("VEC_VERSION", "dev"),
                    details={"path": "data/index/faiss.index.npy", "ok": ok},
                )
            )
        s.commit()
    print("Reindex complete.")

if __name__ == "__main__":
    main()
