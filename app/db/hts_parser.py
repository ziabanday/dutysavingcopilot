
import csv, json, re, argparse
from pathlib import Path
from typing import Dict, Any, Iterable
from app.db.session import SessionLocal, init_db
from app.db.models import HTSItem
from app.utils.logging_setup import get_logger

log = get_logger("hts")

def normalize_code(code: str) -> str:
    code = re.sub(r"\D", "", code or "")
    if len(code) >= 6:
        return f"{code[:4]}.{code[4:6]}" + (f".{code[6:8]}" if len(code)>=8 else "")
    return code

def row_to_obj(row: Dict[str, Any]) -> Dict[str, Any]:
    keys = {k.lower(): v for k, v in row.items()}
    code = keys.get("code") or keys.get("hts") or keys.get("hts_code") or keys.get("hts no") or keys.get("hts number")
    desc = keys.get("description") or keys.get("descr") or keys.get("product description")
    duty = keys.get("duty_rate") or keys.get("duty") or keys.get("general rate") or keys.get("rate")
    chapter = None
    try:
        chapter = int(normalize_code(code).split(".")[0][:2])
    except Exception:
        chapter = None
    return {
        "code": normalize_code(code or ""),
        "description": (desc or "").strip(),
        "duty_rate": (duty or "").strip() or None,
        "chapter": chapter,
        "notes": None,
    }

def iter_csv(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row_to_obj(row)

def iter_json(path: Path) -> Iterable[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("items") or data.get("rows") or data.get("data") or []
    for row in data:
        yield row_to_obj(row)

def load_hts(input_path: str):
    init_db()
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(p)
    it = iter_csv(p) if p.suffix.lower()==".csv" else iter_json(p)
    cnt = 0
    with SessionLocal() as s:
        for obj in it:
            if not obj["code"] or not obj["description"]:
                continue
            s.add(HTSItem(**obj))
            cnt += 1
            if cnt % 1000 == 0:
                s.commit()
        s.commit()
    log.info("Loaded %s HTS rows from %s", cnt, input_path)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input_path", help="CSV or JSON of HTS items")
    args = ap.parse_args()
    load_hts(args.input_path)
