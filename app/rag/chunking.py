from typing import Iterable, Dict, List, Tuple
import re
from app.utils.tokens import count_tokens  # tiny helper (fallback: len(text)//4)

def normalize_text(text: str) -> str:
    text = text.replace("\ufeff", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap: int = 64,
) -> List[Tuple[str, Dict]]:
    """
    Returns list of (chunk_text, meta) with token counts recorded.
    Deterministic boundaries by token-approx; no model calls here.
    """
    words = text.split(" ")
    chunks: List[Tuple[str, Dict]] = []
    cur: List[str] = []
    cur_tok = 0
    for w in words:
        t = max(1, len(w) // 4)  # cheap token approx
        if cur and cur_tok + t > max_tokens:
            ctext = " ".join(cur).strip()
            chunks.append((ctext, {"tokens": count_tokens(ctext)}))
            # overlap by words until ~overlap tokens
            keep: List[str] = []
            tok = 0
            for ww in reversed(cur):
                keep.append(ww)
                tok += max(1, len(ww) // 4)
                if tok >= overlap:
                    break
            cur = list(reversed(keep))
            cur_tok = sum(max(1, len(ww) // 4) for ww in cur)
        cur.append(w)
        cur_tok += t
    if cur:
        ctext = " ".join(cur).strip()
        chunks.append((ctext, {"tokens": count_tokens(ctext)}))
    return chunks

def make_chunk_id(source_id: int, version: int, page: int, idx: int) -> str:
    return f"src:{source_id}:v{version}:p{page}:c{idx}"
