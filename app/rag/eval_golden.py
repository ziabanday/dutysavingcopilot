# app/rag/eval_golden.py
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Local classify entry point
from app.api.routes.classify import classify_query

# Optional: wrapper log lines will appear as usual during embed/chat calls
# (Matches the console you’ve been seeing.)


def _load_golden(path: Path) -> List[Tuple[str, str]]:
    """
    Load golden set as (expected_code, query) pairs.
    Supports CSV with headers like: expected,query  OR  code,query  OR  label,query.
    Also supports JSONL [{"expected": "...", "query": "..."}].
    """
    if path.suffix.lower() == ".jsonl":
        rows: List[Tuple[str, str]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                exp = obj.get("expected") or obj.get("code") or obj.get("label") or ""
                q = obj.get("query") or obj.get("text") or ""
                if exp and q:
                    rows.append((str(exp), str(q)))
        return rows

    # CSV fallback
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        rows = []
        for r in rdr:
            exp = r.get("expected") or r.get("code") or r.get("label") or ""
            q = r.get("query") or r.get("text") or ""
            if exp and q:
                rows.append((str(exp), str(q)))
        return rows


def _codes_from_resp(resp: Dict[str, Any]) -> List[str]:
    try:
        return [c.get("code") for c in resp.get("codes", []) if c.get("code")]
    except Exception:
        return []


def _evidence_ok(resp: Dict[str, Any]) -> bool:
    try:
        codes = resp.get("codes", [])
        if not codes:
            return False
        return all(bool(c.get("evidence")) for c in codes)
    except Exception:
        return False


def run_eval(k: int, metrics_path: Path | None) -> None:
    golden_path = Path("data/golden/golden_set.csv")
    rows = _load_golden(golden_path)
    if not rows:
        print(f"[eval] no golden rows found at {golden_path}")
        return

    # warmup (embedding + chat) — same log style you saw in your console
    from app.core.openai_wrapper import warmup  # type: ignore
    warmup()

    latencies: List[float] = []
    hit_top1 = 0
    hit_topk = 0
    ev_count = 0

    # ---- Canonical metrics CSV (per-query rows) ----
    writer = None
    if metrics_path:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        header = ["run_id", "k", "top1_hit", "top3_hit", "evidence_covered", "lat_ms"]
        write_header = (not metrics_path.exists()) or (metrics_path.stat().st_size == 0)
        f_metrics = metrics_path.open("a", encoding="utf-8", newline="")
        writer = csv.DictWriter(f_metrics, fieldnames=header)
        if write_header:
            writer.writeheader()
    else:
        f_metrics = None  # type: ignore[assignment]

    try:
        for i, (expected, query) in enumerate(rows, start=1):
            t0 = time.perf_counter()
            inst, raw = classify_query(query)
            lat_s = time.perf_counter() - t0
            latencies.append(lat_s)

            got = _codes_from_resp(raw)[:k]
            top1_contains = 1 if (got and got[0] == expected) else 0
            topk_contains = 1 if (expected in got) else 0
            evidence_hits = 1 if _evidence_ok(raw) else 0

            if top1_contains:
                hit_top1 += 1
            if topk_contains:
                hit_topk += 1
            if evidence_hits:
                ev_count += 1

            # --- canonical metrics row ---
            # Per your request: write one row per query with these exact columns.
            if writer is not None:
                run_id = datetime.now(timezone.utc).isoformat(timespec="seconds")
                row = {
                    "run_id": run_id,
                    "k": str(k),  # ensure '1' or '3'
                    "top1_hit": int(top1_contains),
                    "top3_hit": int(topk_contains),
                    "evidence_covered": int(evidence_hits),
                    "lat_ms": float(lat_s * 1000.0),
                }
                writer.writerow(row)

            print(
                f"[{i}/{len(rows)}] expected={expected} got={got}  "
                f"lat={lat_s:.2f}s  evidence={'1' if evidence_hits else '0'}"
            )
    finally:
        # Close the metrics file if we opened it
        try:
            if metrics_path and f_metrics:
                f_metrics.close()
        except Exception:
            pass

    p50 = statistics.median(latencies) if latencies else 0.0
    top1 = hit_top1 / len(rows) if rows else 0
    topk = hit_topk / len(rows) if rows else 0

    if k == 1:
        print(f"\nTop-1 contains: {top1*100:.1f}% ({hit_top1}/{len(rows)}); p50 latency: {p50:.2f}s")
    else:
        print(f"\nTop-{k} contains: {topk*100:.1f}% ({hit_topk}/{len(rows)}); p50 latency: {p50:.2f}s")


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--k", type=int, default=3, help="Top-K to test: 1 or 3")
    p.add_argument("--write-metrics", default="", help="Path to append CSV metrics (optional)")
    args = p.parse_args(argv)

    metrics = Path(args.write_metrics) if args.write_metrics else None
    run_eval(k=args.k, metrics_path=metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
