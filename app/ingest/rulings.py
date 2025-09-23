import argparse, json, os
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

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
        url = os.getenv("DATABASE_URL", "sqlite:///local.db")
        kw = {"check_same_thread": False} if url.startswith("sqlite") else {}
        return create_engine(url, connect_args=kw, future=True)

from app.db.models import SourceDocument, Chunk
from app.rag.chunking import normalize_text, chunk_text, make_chunk_id
from app.core.openai_wrapper import embed, is_stub_mode

# Prefer Week-1 helper if available
try:
    from app.db.cross_ingest import fetch_ruling_html  # type: ignore
except Exception:
    def fetch_ruling_html(ruling_id: str) -> str:
        raise RuntimeError(
            "fetch_ruling_html(...) not available. "
            "Provide raw HTML in data/rulings/raw/{ruling_id}.html or implement the helper."
        )

def embed_and_attach(session: Session, chunks):
    for c in chunks:
        try:
            c.embedding = embed(c.text)
        except Exception as e:
            print(f"[ingest.rulings] embedding failed chunk={c.chunk_id}: {e}")
    session.commit()

def normalize_ruling(ruling_id: str) -> dict:
    raw_path = os.path.join("data", "rulings", "raw", f"{ruling_id}.html")
    if not os.path.exists(raw_path):
        html = fetch_ruling_html(ruling_id)
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)
        open(raw_path, "w", encoding="utf-8").write(html)
    else:
        html = open(raw_path, "r", encoding="utf-8").read()

    txt = normalize_text(html)
    norm_path = os.path.join("data", "rulings", "normalized", f"{ruling_id}.jsonl")
    os.makedirs(os.path.dirname(norm_path), exist_ok=True)
    with open(norm_path, "w", encoding="utf-8") as f:
        for para in txt.split("\n\n"):
            if para.strip():
                f.write(json.dumps({"ruling_id": ruling_id, "text": para.strip()}, ensure_ascii=False) + "\n")
    return {"path": norm_path, "url": None}

def upsert_ruling(session: Session, ruling_id: str, max_tokens: int, overlap: int, do_embed: bool):
    meta = normalize_ruling(ruling_id)
    src = SourceDocument(
        source_type="ruling",
        external_id=ruling_id,
        title=f"Ruling {ruling_id}",
        version=1,
        meta=meta,
    )
    session.add(src)
    session.flush()

    # stream normalized jsonl
    texts = [json.loads(l)["text"] for l in open(meta["path"], "r", encoding="utf-8")]
    parts = []
    for t in texts:
        parts.extend(chunk_text(t, max_tokens=max_tokens, overlap=overlap))

    payload = []
    for idx, (ctext, m) in enumerate(parts):
        cid = make_chunk_id(src.id, src.version, page=0, idx=idx)
        payload.append(Chunk(source_id=src.id, chunk_id=cid, text=ctext, page=0, idx=idx, meta=m))
    session.add_all(payload)
    session.commit()

    if do_embed and not is_stub_mode():
        embed_and_attach(session, payload)

    return src.id, len(payload)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids-file", required=True)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=64)
    ap.add_argument("--no-embed", action="store_true")
    args = ap.parse_args()

    engine = _resolve_engine()
    with Session(engine) as s:
        ids = [l.strip() for l in open(args.ids_file, "r", encoding="utf-8-sig") if l.strip()]
        for rid in ids:
            sid, n = upsert_ruling(s, rid, args.max_tokens, args.overlap, do_embed=not args.no_embed)
            print(f"[ingest.rulings] ingested source_id={sid}, chunks={n}, id={rid}")
    print("Rulings ingestion complete.")

if __name__ == "__main__":
    main()
