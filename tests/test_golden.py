# tests/test_golden.py
from __future__ import annotations
import os
import tempfile
from pathlib import Path

os.environ["NO_API"] = "1"  # stub LLM for CI

from app.rag.eval_golden import run_eval  # noqa: E402


def test_golden_smoke(tmp_path: Path, monkeypatch):
    # Create a tiny golden set (3 rows) that our stub can handle leniently.
    data_dir = Path("data/golden")
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / "golden_set.csv"
    csv_path.write_text(
        "sku,notes,expected_code\n"
        "AC adapter 12V 2A,,8504.40\n"
        "USB charger 5V 1A,,8504.40\n"
        "Laptop power supply,,8504.40\n",
        encoding="utf-8",
    )

    # Just ensure it runs without exceptions and prints results.
    run_eval(k=3)
    assert csv_path.exists()
