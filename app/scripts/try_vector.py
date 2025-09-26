# app/scripts/try_vector.py
from __future__ import annotations
import argparse, json, os, uuid, datetime as dt, decimal
from typing import List, Dict, Any
from app.retrieve.vector_search import vector_topk

def _json_default(o):
    if isinstance(o, (uuid.UUID, dt.datetime, dt.date, dt.time)):
        return str(o)
    if isinstance(o, decimal.Decimal):
        return float(o)
    # last resort
    return str(o)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--q", "--query", dest="query", required=True, help="query text")
    p.add_argument("--k", type=int, default=6, help="top-k")
    args = p.parse_args()

    hits: List[Dict[str, Any]] = vector_topk(args.query, k=args.k)

    # optional guardrail: MIN_SCORE env
    try:
        min_score = float(os.getenv("MIN_SCORE", "0"))
        hits = [h for h in hits if h.get("score") is None or h["score"] >= min_score]
    except Exception:
        pass

    print(json.dumps(hits, indent=2, ensure_ascii=False, default=_json_default))

if __name__ == "__main__":
    main()
