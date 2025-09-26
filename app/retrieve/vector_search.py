# app/retrieve/vector_search.py
# Robust pgvector Top-K that adapts to your actual schema.

from __future__ import annotations
from pathlib import Path
import os
import typing as t

import sqlalchemy as sa
from sqlalchemy import text, event
from dotenv import load_dotenv

from app.db.session import engine, get_session

# --- pgvector adapter (psycopg3) ---
try:
    from pgvector.psycopg import register_vector  # type: ignore
except Exception:
    register_vector = None

if register_vector is not None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _):
        try:
            register_vector(dbapi_conn)
        except Exception:
            pass

# --- Optional embeddings (falls back to zero-vector) ---
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

EMBED_DIM = 1536


def _embed_query(q: str) -> t.List[float]:
    """Return a 1536-dim embedding for q, or zeros if no OPENAI_API_KEY."""
    key = os.getenv("OPENAI_API_KEY")
    if not key or key == "xxxxxxxx" or OpenAI is None:
        return [0.0] * EMBED_DIM
    client = OpenAI(api_key=key)
    resp = client.embeddings.create(model="text-embedding-3-small", input=[q])
    return resp.data[0].embedding


def _schema() -> dict:
    """Reflect minimal schema and pick the correct column names."""
    meta = sa.MetaData()
    meta.reflect(bind=engine, only=["source_documents", "chunks"])
    sd = meta.tables["source_documents"]
    ck = meta.tables["chunks"]

    def pick(cols, *names):
        for n in names:
            if n in cols:
                return n
        return None

    # label on source_documents
    sd_label = pick(sd.c, "source", "title", "name", "collection", "label") or "title"

    # optional URI-ish column on source_documents
    sd_uri = pick(sd.c, "uri", "source_path")

    # foreign key on chunks -> source_documents.id
    fk = pick(ck.c, "source_document_id", "source_doc_id", "document_id", "doc_id") or "doc_id"

    # chunk text/content column
    ctext = pick(ck.c, "content", "text", "chunk_text", "body") or "content"

    # chunk metadata/json column (optional)
    cmeta = pick(ck.c, "metadata", "meta")

    return dict(sd_label=sd_label, sd_uri=sd_uri, fk=fk, ctext=ctext, cmeta=cmeta)


def vector_topk(query: str, k: int = 6) -> t.List[dict]:
    """Return a list of results with fields: chunk_id, doc_title, source, uri, content, score, chunk_metadata."""
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)

    qvec = _embed_query(query)
    S = _schema()

    # Build SELECT list adapting to available columns
    select_cols = [
        "c.id::text AS chunk_id",
        f"sd.{S['sd_label']} AS doc_title",
        f"sd.{S['sd_label']} AS source",  # expose a 'source' field
        (f"sd.{S['sd_uri']} AS uri" if S["sd_uri"] else "NULL AS uri"),
        f"c.{S['ctext']} AS content",
        # >>> Cast the parameter to pgvector(1536) <<<
        "1.0 - (c.embedding <=> CAST(:qvec AS vector(1536))) AS score",
        (f"c.{S['cmeta']} AS chunk_metadata" if S["cmeta"] else "NULL AS chunk_metadata"),
    ]

    sql = text(
        f"""
        SELECT
            {", ".join(select_cols)}
        FROM chunks c
        JOIN source_documents sd ON sd.id = c.{S['fk']}
        ORDER BY c.embedding <=> CAST(:qvec AS vector(1536))
        LIMIT :k
        """
    )

    with get_session() as session:
        rows = session.execute(sql, {"qvec": qvec, "k": k}).mappings().all()
    return [dict(r) for r in rows]
