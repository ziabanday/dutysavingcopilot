"""
HTSUS 84–85 loader (Phase-6 scaffolding)
 - Deterministic IDs & chunking
 - Dev/offline path: lightweight SQLite (or in-repo JSONL sink)
 - Prod/smoke path: pgvector guarded by PG_DSN/DATABASE_URL
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional, Dict, Any, Tuple
import hashlib
import json
import os

HTS_DIR = Path("data/htsus")  # expected: JSON/JSONL per heading/subheading

@dataclass(frozen=True)
class Doc:
    doc_id: str
    title: str
    edition: Optional[str]
    source: str
    meta: Dict[str, Any]
    text: str

@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    meta: Dict[str, Any]

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _doc_id_for(ch: int, heading: str, edition: Optional[str]) -> str:
    # htsus:{chapter}:{heading}[.{sub}]@{edition}
    base = f"htsus:{ch}:{heading}"
    return f"{base}@{edition}" if edition else base

def _chunk_id(doc_id: str, section_idx: int, offset: int) -> str:
    return f"{doc_id}#s{section_idx}-o{offset:06d}"

def _deterministic_chunks(text: str, window: int = 800, overlap: int = 120) -> Iterator[Tuple[int, int, str]]:
    """
    Deterministic fixed-window splitter. Sorted, no randomness.
    Yields (section_idx, offset, chunk_text).
    """
    i = 0
    section = 0
    n = len(text)
    while i < n:
        j = min(i + window, n)
        yield section, i, text[i:j]
        if j == n:
            break
        i = j - overlap
        section += 1

def _iter_htsus_files(chapter: int) -> Iterator[Path]:
    # Accept both *.jsonl and *.json under data/htsus/{chapter}/
    base = HTS_DIR / str(chapter)
    if not base.exists():
        return iter(())
    yield from sorted(base.rglob("*.jsonl"))
    yield from sorted(base.rglob("*.json"))

def _read_docs(chapter: int) -> Iterator[Doc]:
    """
    Expected record shape (flexible):
    { "heading":"8407.10", "title":"...", "edition":"2025-01-01", "text":"..." }
    """
    for p in _iter_htsus_files(chapter):
        if p.suffix == ".jsonl":
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                doc_id = _doc_id_for(chapter, rec["heading"], rec.get("edition"))
                yield Doc(
                    doc_id=doc_id,
                    title=rec.get("title") or rec["heading"],
                    edition=rec.get("edition"),
                    source="htsus",
                    meta={"chapter": chapter, "heading": rec["heading"], "path": str(p)},
                    text=rec["text"],
                )
        else:
            rec = json.loads(p.read_text(encoding="utf-8"))
            doc_id = _doc_id_for(chapter, rec["heading"], rec.get("edition"))
            yield Doc(
                doc_id=doc_id,
                title=rec.get("title") or rec["heading"],
                edition=rec.get("edition"),
                source="htsus",
                meta={"chapter": chapter, "heading": rec["heading"], "path": str(p)},
                text=rec["text"],
            )

def load_htsus(chapters: Iterable[int], sink: str = "sqlite") -> Dict[str, int]:
    """
    Idempotent ingest. For Phase-6 scaffolding, we implement:
      - 'sqlite' sink: writes NDJSON “tables” under artifacts/devdb/ (dev/offline)
      - 'pg' sink: returns counts; actual INSERTs are provided by the CLI via pg-guarded repo (next step)
    Returns counts: {"docs": N, "chunks": M}
    """
    counts = {"docs": 0, "chunks": 0}
    assert sink in {"sqlite", "pg"}
    out_root = Path("artifacts/devdb/htsus")
    out_root.mkdir(parents=True, exist_ok=True)

    for ch in sorted(set(int(c) for c in chapters)):
        for d in _read_docs(ch):
            # Emit deterministic chunks
            chunk_file = (out_root / f"{_sha(d.doc_id)}.chunks.jsonl")
            doc_file = (out_root / f"{_sha(d.doc_id)}.doc.json")

            if not doc_file.exists():
                doc_file.write_text(json.dumps({
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "edition": d.edition,
                    "source": d.source,
                    "meta": d.meta,
                    "hash": _sha(d.text),
                }, ensure_ascii=False), encoding="utf-8")
                counts["docs"] += 1

            # Append-safe, idempotent by chunk_id
            existing = set()
            if chunk_file.exists():
                for line in chunk_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    existing.add(json.loads(line)["chunk_id"])

            with chunk_file.open("a", encoding="utf-8") as w:
                for s_idx, offset, chunk_text in _deterministic_chunks(d.text):
                    cid = _chunk_id(d.doc_id, s_idx, offset)
                    if cid in existing:
                        continue
                    w.write(json.dumps({
                        "chunk_id": cid,
                        "doc_id": d.doc_id,
                        "text": chunk_text,
                        "meta": {"section": s_idx, "offset": offset},
                    }, ensure_ascii=False) + "\n")
                    counts["chunks"] += 1

    # For 'pg' sink in this scaffolding step, we only ensure the path runs.
    # Actual pg INSERTs + embeddings wiring will be in Step 3 (CI smoke gate).
    return counts
