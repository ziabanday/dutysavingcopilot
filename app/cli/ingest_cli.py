from __future__ import annotations
import argparse
import os
from app.ingest.load_htsus import load_htsus

def main():
    parser = argparse.ArgumentParser("ingest_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_htsus = sub.add_parser("htsus", help="Ingest HTSUS chapters (e.g. 84 85)")
    p_htsus.add_argument("chapters", nargs="+", type=int)
    p_htsus.add_argument("--pg", action="store_true", help="Use pg sink (guarded by PG_DSN/DATABASE_URL)")

    args = parser.parse_args()
    if args.cmd == "htsus":
        sink = "pg" if args.pg and (os.getenv("PG_DSN") or os.getenv("DATABASE_URL")) else "sqlite"
        counts = load_htsus(args.chapters, sink=sink)
        print({"ok": True, "sink": sink, **counts})

if __name__ == "__main__":
    main()
