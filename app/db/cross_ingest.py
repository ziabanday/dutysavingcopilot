# app/db/cross_ingest.py
import re
import argparse
import datetime as dt
from typing import List, Dict, Any, Optional
from pathlib import Path

import requests

from app.db.session import SessionLocal, init_db
from app.db.models import Ruling, RulingChunk
from app.core.openai_wrapper import embed
from app.core.settings import OPENAI_EMBED_MODEL
from app.utils.logging_setup import get_logger

log = get_logger("cross")

CBP_BASE = "https://rulings.cbp.gov/ruling/"


def fetch_ruling(rid: str) -> Dict[str, Any]:
    """Fetch a ruling page and return parsed fields (very light parsing)."""
    rid_clean = rid.strip().lstrip("\ufeff")
    url = CBP_BASE + rid_clean.replace(" ", "%20")
    headers = {"User-Agent": "HTS-Copilot/0.1 (dev)"}

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    html = r.text

    # CBP site is Angular; if we can't find the body, fall back to whole HTML
    body = re.search(r'<div[^>]*class="ruling-body"[^>]*>([\s\S]*?)</div>', html, re.I)
    text = re.sub("<[^>]+>", " ", body.group(1)) if body else html
    text = re.sub(r"\s+", " ", text).strip()

    # Heuristic: any 4-2 or 4-2-2 HTS pattern mentioned in the text
    codes = sorted(set(re.findall(r"\b(\d{4}\.\d{2}(?:\.\d{2})?)\b", text)))

    # Try to parse a date like "January 1, 2022"
    dmatch = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        html,
    )
    rdate: Optional[dt.date] = None
    if dmatch:
        try:
            rdate = dt.datetime.strptime(dmatch.group(0), "%B %d, %Y").date()
        except Exception:
            rdate = None

    return {
        "ruling_id": rid_clean,
        "hts_codes": codes,
        "url": url,
        "text": text,
        "date": rdate,
    }


def chunk_text(text: str, target_tokens: int = 1000) -> List[str]:
    """Naive chunking by characters; ~4 chars per token."""
    max_chars = target_tokens * 4
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def read_ids_from_file(path: Path) -> List[str]:
    """Read IDs from file, stripping BOM if present."""
    raw = path.read_text(encoding="utf-8-sig")  # strips BOM automatically
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def ingest_rulings(ids: List[str], chunk_version: str = "v0.1", do_embed: bool = True):
    """Idempotent ingest of rulings. Skips already-present ruling_ids."""
    init_db()
    with SessionLocal() as s:
        seen = set()
        for rid in ids:
            rid = rid.strip().lstrip("\ufeff")
            if not rid or rid in seen:
                continue
            seen.add(rid)

            # Skip if already ingested
            if s.query(Ruling).filter_by(ruling_id=rid).first():
                log.info("Ruling %s already exists; skipping.", rid)
                continue

            # Fetch + store ruling
            data = fetch_ruling(rid)
            r = Ruling(
                ruling_id=data["ruling_id"],
                hts_codes=data["hts_codes"],
                url=data["url"],
                text=data["text"],
                ruling_date=data["date"],
            )
            s.add(r)
            s.flush()  # get r.id

            # Chunk + (optionally) embed
            texts = [c for c in chunk_text(data["text"], 1000) if c.strip()]
            if not texts:
                log.info("Ruling %s has no text to chunk; skipping chunks.", rid)
                s.commit()
                continue

            if do_embed:
                emb = embed(texts)
                vectors = [row.embedding for row in emb["response"].data]
            else:
                vectors = [None] * len(texts)

            for idx, (txt, vec) in enumerate(zip(texts, vectors)):
                s.add(
                    RulingChunk(
                        ruling_id_fk=r.id,
                        chunk_index=idx,
                        text=txt,
                        embedding=vec,
                        embedding_model=OPENAI_EMBED_MODEL if do_embed else None,
                        chunk_version=chunk_version,
                    )
                )
            s.commit()
            log.info(
                "Ingested ruling %s with %d chunks (embed=%s)",
                rid,
                len(texts),
                do_embed,
            )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", help="Ruling IDs e.g. NY N123456")
    ap.add_argument(
        "--ids-file", type=str, help="Text file with one ruling ID per line"
    )
    ap.add_argument(
        "--no-embed", action="store_true", help="Skip embeddings (cheaper dry run)"
    )
    args = ap.parse_args()

    ids: List[str] = []
    if args.ids:
        ids.extend(args.ids)
    if args.ids_file:
        ids.extend(read_ids_from_file(Path(args_ids_file := args.ids_file)))
    if not ids:
        ap.error("Provide --ids or --ids-file")

    ingest_rulings(ids, do_embed=(not args.no_embed))
