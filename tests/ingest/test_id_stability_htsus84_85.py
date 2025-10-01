*** Begin Patch
*** Add File: tests/ingest/test_id_stability_htsus84_85.py
+import os
+import pytest
+from pathlib import Path
+from app.ingest.load_htsus import load_htsus
+
+DATA84 = Path("data/htsus/84")
+DATA85 = Path("data/htsus/85")
+
+@pytest.mark.skipif(not (DATA84.exists() or DATA85.exists()), reason="pilot data not present")
+def test_ids_are_deterministic(tmp_path, monkeypatch):
+    # Redirect devdb to a temp folder for test isolation
+    monkeypatch.chdir(tmp_path)
+    (tmp_path / "data" / "htsus" / "84").mkdir(parents=True, exist_ok=True)
+    # Minimal synthetic sample
+    sample = (tmp_path / "data" / "htsus" / "84" / "8407.10.json")
+    sample.write_text('{"heading":"8407.10","edition":"2025-01-01","title":"8407.10","text":"A"*2500}', encoding="utf-8")
+
+    c1 = load_htsus([84], sink="sqlite")
+    c2 = load_htsus([84], sink="sqlite")
+    # Idempotent: second run shouldn't add new docs/chunks
+    assert c1["docs"] >= 1
+    assert c1["chunks"] >= 1
+    assert c2["docs"] == 0
+    assert c2["chunks"] == 0
+
*** End Patch
