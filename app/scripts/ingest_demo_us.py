# app/scripts/ingest_demo_us.py
# POC ingest: inserts 5 demo chunks under a single source document.
# Robust to schema differences (title vs source; doc_id vs source_document_id).
# Uses pgvector (1536-dim) and works even without OpenAI (falls back to zero vectors).

from __future__ import annotations
from pathlib import Path
import os, sys, typing as t, hashlib
import datetime as dt

import sqlalchemy as sa
from sqlalchemy import event
from dotenv import load_dotenv

from app.db.session import engine, get_session

# --- pgvector adapter (psycopg3) so Python lists -> 'vector' type ---
try:
    from pgvector.psycopg import register_vector  # psycopg3 adapter
except Exception:
    register_vector = None

if register_vector is not None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _):
        try:
            register_vector(dbapi_conn)
        except Exception:
            # safe no-op if already registered
            pass

# --- Optional embeddings (zero-vectors if no key) ---
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

DEMO_SOURCE = "demo/us_hts_poc"
DEMO_TEXTS = [
    "Classify electric motor HS code with duty implications.",
    "Motherboard classification guidance for laptops.",
    "Tariff note on parts vs. accessories distinction.",
    "General HTS classification workflow for electronics.",
    "CROSS ruling cues: subheading notes for PC components.",
]

def _reflect():
    meta = sa.MetaData()
    # You may still see a harmless SAWarning about 'vector' during reflection.
    meta.reflect(bind=engine, only=["source_documents", "chunks"])
    return meta.tables["source_documents"], meta.tables["chunks"]

def _pick(colset: sa.sql.base.ReadOnlyColumnCollection, *names: str) -> sa.Column:
    for n in names:
        if n in colset:
            return colset[n]
    raise RuntimeError(f"Could not find any of {names} in columns: {[c.name for c in colset]}")

def _detect(sd: sa.Table, ck: sa.Table):
    # Choose a label column on source_documents (whichever exists)
    sd_id = _pick(sd.c, "id")
    sd_label = None
    for cand in ("source", "title", "name", "collection", "label"):
        if cand in sd.c:
            sd_label = sd.c[cand]
            break
    if sd_label is None:
        raise RuntimeError("No label column found on source_documents (expected one of source/title/name/collection/label)")

    # chunks foreign key & core columns
    ck_id   = _pick(ck.c, "id")
    ck_sdoc = _pick(ck.c, "source_document_id", "source_doc_id", "document_id", "doc_id")
    ck_text = _pick(ck.c, "content", "text", "chunk_text", "body")
    ck_vec  = _pick(ck.c, "embedding", "vector", "embedding_1536")

    return dict(sd=sd, ck=ck, sd_id=sd_id, sd_label=sd_label,
                ck_id=ck_id, ck_sdoc=ck_sdoc, ck_text=ck_text, ck_vec=ck_vec)

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def _embed_texts(texts: t.List[str]) -> t.List[t.List[float]]:
    # Fall back to zero-vectors to keep the DB pipeline testable without API keys.
    if OpenAI is None or not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "xxxxxxxx":
        return [[0.0] * 1536 for _ in texts]
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]

def _fill_required_sd_values(sd: sa.Table, label_col: sa.Column, label_value: str, all_texts: str) -> dict:
    """
    Provide values for NOT NULL columns on source_documents.
    Always sets the label column; conditionally fills common fields if present.
    """
    values = {label_col.key: label_value}

    # Common optional/required columns we can populate
    if "source_path" in sd.c:
        values["source_path"] = f"demo://{label_value}"
    if "source_hash" in sd.c:
        values["source_hash"] = _sha1(values.get("source_path", label_value))
    if "content_hash" in sd.c:
        values["content_hash"] = _sha1(all_texts)
    if "meta" in sd.c:
        values["meta"] = {}  # JSON/JSONB
    if "created_at" in sd.c:
        values["created_at"] = dt.datetime.now(dt.timezone.utc)

    # Catch-all for any other NOT NULL column without a default
    for col in sd.c:
        if col.primary_key or col.name in values:
            continue
        no_default = (col.default is None and col.server_default is None)
        if no_default and not col.nullable:
            tpe = type(col.type).__name__.lower()
            if "int" in tpe or "num" in tpe:
                values[col.name] = 0
            elif "bool" in tpe:
                values[col.name] = False
            elif "json" in tpe:
                values[col.name] = {}
            elif "date" in tpe or "time" in tpe:
                values[col.name] = dt.datetime.now(dt.timezone.utc)
            else:
                values[col.name] = label_value  # generic string-ish
    return values

def _maybe_add_required_chunk_fields(ck: sa.Table, base_row: dict, ord_index: int) -> dict:
    row = dict(base_row)
    if "chunk_ord" in ck.c and "chunk_ord" not in row:
        row["chunk_ord"] = ord_index
    if "meta" in ck.c and "meta" not in row:
        row["meta"] = {}
    if "created_at" in ck.c and "created_at" not in row:
        row["created_at"] = dt.datetime.now(dt.timezone.utc)
    return row

def main() -> int:
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)

    sd, ck = _reflect()
    cols = _detect(sd, ck)

    all_texts = "\n".join(DEMO_TEXTS)
    vectors = _embed_texts(DEMO_TEXTS)
    if len(vectors) != len(DEMO_TEXTS):
        print("embedding count mismatch", file=sys.stderr)
        return 2

    with get_session() as s:
        # Clean any previous demo rows
        s.execute(
            sa.delete(ck).where(
                cols["ck_sdoc"].in_(
                    sa.select(cols["sd_id"]).where(cols["sd_label"] == DEMO_SOURCE)
                )
            )
        )
        s.execute(sa.delete(sd).where(cols["sd_label"] == DEMO_SOURCE))

        # Insert source_document with all required fields satisfied
        sd_values = _fill_required_sd_values(sd, cols["sd_label"], DEMO_SOURCE, all_texts)
        doc_id = s.execute(
            sa.insert(sd).values(sd_values).returning(cols["sd_id"])
        ).scalar_one()

        # Insert chunks
        rows: list[dict] = []
        for i, (text_, vec_) in enumerate(zip(DEMO_TEXTS, vectors), start=1):
            base = {
                cols["ck_sdoc"].key: doc_id,
                cols["ck_text"].key: text_,
                cols["ck_vec"].key: vec_,
            }
            rows.append(_maybe_add_required_chunk_fields(ck, base, i))

        s.execute(sa.insert(ck), rows)
        s.commit()

    print(f"Inserted {len(rows)} demo chunks under label='{DEMO_SOURCE}' (doc_id={doc_id})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
