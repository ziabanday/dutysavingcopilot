import re, argparse, datetime as dt
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
    url = CBP_BASE + rid.replace(" ", "%20")
    headers = {"User-Agent": "HTS-Copilot/0.1 (dev)"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    html = r.text

    # Very light scraping; CBP is an Angular app so we fall back to full HTML when body not found
    body = re.search(r'<div[^>]*class="ruling-body"[^>]*>([\s\S]*?)</div>', html, re.I)
    text = re.sub("<[^>]+>", " ", body.group(1)) if body else html
    text = re.sub(r"\s+", " ", text).strip()

    # Guess HTS codes mentioned
    codes = sorted(set(re.findall(r"\b(\d{4}\.\d{2}(?:\.\d{2})?)\b", text)))

    # Try to parse a date
    dmatch = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}", html)
    rdate: Optional[dt.date] = None
    if dmatch:
        try:
            rdate = dt.datetime.strptime(dmatch.group(0), "%B %d, %Y").date()
        except Exception:
            rdate = None

    return {"ruling_id": rid, "hts_codes": codes, "url": url, "text": text, "date": rdate}

def chunk_text(text: str, target_tokens: int = 1000):
    # naive tokens ~= chars/4
    max_chars = target_tokens * 4
    return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]

def read_ids_from_file(path: Path) -> List[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def ingest_rulings(ids: List[str], chunk_version: str = "v0.1", do_embed: bool = True):
    init_db()
    with SessionLocal() as s:
        for rid in ids:
            data = fetch_ruling(rid)
            r = Ruling(
                ruling_id=data["ruling_id"],
                hts_codes=data["hts_codes"],
                url=data["url"],
                text=data["text"],
                ruling_date=data["date"],
            )
            s.add(r); s.flush()  # get r.id

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
                s.add(RulingChunk(
                    ruling_id_fk=r.id,
                    chunk_index=idx,
                    text=txt,
                    embedding=vec,
                    embedding_model=OPENAI_EMBED_MODEL if do_embed else None,
                    chunk_version=chunk_version
                ))
            s.commit()
            log.info("Ingested ruling %s with %d chunks (embed=%s)", rid, len(texts), do_embed)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", help="Ruling IDs e.g. NY N123456")
    ap.add_argument("--ids-file", type=str, help="Text file with one ruling ID per line")
    ap.add_argument("--no-embed", action="store_true", help="Skip embeddings (cheaper dry run)")
    args = ap.parse_args()

    ids: List[str] = []
    if args.ids:
        ids.extend(args.ids)
    if args.ids_file:
        ids.extend(read_ids_from_file(Path(args.ids_file)))
    if not ids:
        ap.error("Provide --ids or --ids-file")

    ingest_rulings(ids, do_embed=(not args.no_embed))
