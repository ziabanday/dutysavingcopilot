import json, io, glob, argparse, os
from typing import List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# Try to reuse project's engine; fallback to DATABASE_URL
def _resolve_engine():
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

def embed_and_attach(session: Session, chunks: List[Chunk]) -> None:
    for c in chunks:
        try:
            c.embedding = embed(c.text)
        except Exception as e:
            print(f"[ingest.hts] embedding failed chunk={c.chunk_id}: {e}")
    session.commit()

def _upsert_one_item(session: Session, payload: Dict[str, Any],
                     max_tokens: int, overlap: int,
                     do_embed: bool) -> Tuple[str, int]:
    """
    Upsert a single HTS item shaped like:
      {"code": "8504.40", "title": "...", "text": "..."}
    """
    code = payload.get("code") or "UNKNOWN"
    title = payload.get("title") or code
    raw_text = payload.get("text") or ""

    # Normalize text (handles whitespace/newlines)
    text = normalize_text(raw_text)
    parts = chunk_text(text, max_tokens=max_tokens, overlap=overlap)

    # SourceDocument — one per HTS item (code/title)
    prev = (
        session.query(SourceDocument)
        .filter_by(source_type="hts", external_id=code)
        .order_by(SourceDocument.version.desc())
        .first()
    )
    version = 1 if not prev else prev.version + 1

    src = SourceDocument(
        source_type="hts",
        external_id=code,
        title=title,
        version=version,
        meta={"code": code, "title": title},
    )
    session.add(src)
    session.flush()

    chunks = []
    for idx, (ctext, meta) in enumerate(parts):
        cid = make_chunk_id(src.id, src.version, page=0, idx=idx)
        chunks.append(
            Chunk(
                source_id=src.id,
                chunk_id=cid,
                text=ctext,
                page=0,
                idx=idx,
                meta={"code": code, "title": title, **(meta or {})},
            )
        )
    if chunks:
        session.add_all(chunks)
        session.commit()

    if do_embed and chunks and not is_stub_mode():
        embed_and_attach(session, chunks)

    return code, len(chunks)

def upsert_hts(session: Session, path: str,
               max_tokens: int, overlap: int,
               do_embed: bool) -> Tuple[str, int]:
    """
    Ingest file at `path`. Accepts either:
      - dict with {"title": "...", "items": [ {code,title,text}, ... ]}
      - dict with {"code","title","text"} (single)
      - list of {code,title,text} objects
    """
    # BOM-tolerant read
    with io.open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    total_chunks = 0
    first_id = None

    # Case A: dict with items[]
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data["items"]
    # Case B: list of items
    elif isinstance(data, list):
        items = data
    # Case C: single item-like dict
    elif isinstance(data, dict) and ("text" in data or "code" in data):
        items = [data]
    else:
        # Fallback: treat whole dict as one text blob (legacy)
        items = [{"code": data.get("code") or os.path.basename(path),
                  "title": data.get("title") or os.path.basename(path),
                  "text": json.dumps(data, ensure_ascii=False)}]

    for it in items:
        code, n = _upsert_one_item(session, {
            "code": it.get("code"),
            "title": it.get("title"),
            "text": it.get("text"),
        }, max_tokens, overlap, do_embed)
        if first_id is None:
            first_id = code
        total_chunks += n

    return first_id or "NA", total_chunks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", nargs="+", default=glob.glob("data/hts/*.json"))
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=64)
    ap.add_argument("--no-embed", action="store_true")
    args = ap.parse_args()

    engine = _resolve_engine()
    with Session(engine) as s:
        for p in args.src:
            if not os.path.exists(p):
                print(f"[ingest.hts] skip (missing): {p}")
                continue
            sid, n = upsert_hts(s, p, args.max_tokens, args.overlap, do_embed=not args.no_embed)
            print(f"[ingest.hts] ingested id={sid}, chunks={n}, path={p}")
    print("HTS ingestion complete.")

if __name__ == "__main__":
    main()
