*** Begin Patch
*** Add File: docs/ingest.md
+# Ingestion & Ops Guide — Week-6 Free Datasets Pilot (HTSUS 84–85)
+
+This guide is **Windows-first** with **Docker parity**, designed for **offline-first** determinism and an optional **online pgvector** path when `PG_DSN` (or `DATABASE_URL`) is available.
+
+## 0) Prereqs
+- Python 3.11+ with virtualenv
+- Git, PowerShell
+- (Optional) Docker Desktop
+- Repo cloned and tests green offline
+
+## 1) Environment Matrix (quick reference)
+| Mode | Required | Recommended | Notes |
+|---|---|---|---|
+| **DEV (offline)** | `NO_NETWORK=1`, `OPENAI_API_MOCK=1` | `STRICT_JSON=1`, `ABSTAIN_ON_NO_EVIDENCE=1`, `MIN_SCORE=0.40` | Runs ingestion + eval without external calls. |
+| **CI (offline)** | Same as DEV | Metrics flags (see below) | Deterministic; uploads metrics artifact. |
+| **PROD/Smoke (online)** | `PG_DSN` **or** `DATABASE_URL` (pgvector DSN) | `STRICT_JSON=1`, `MIN_SCORE=0.40` | Gated in CI; only runs when DSN is present. |
+
+> **DSN naming:** If both are set, `PG_DSN` takes precedence; otherwise we fall back to `DATABASE_URL`.
+
+### Common flags
+- `METRICS_DIR=artifacts/metrics` (folder will be created if absent)
+- `METRICS_JSONL=1` (enable JSONL callback from `app/metrics/cb.py`)
+- `W_BM25=0.6` `W_VEC=0.4` (default RRF/fusion knobs; override as needed)
+
+## 2) Quickstart — Windows (offline-first)
+```powershell
+# 0) Activate venv
+. .\.venv\Scripts\Activate.ps1
+
+# 1) Safety: offline + strict
+$env:NO_NETWORK = '1'
+$env:OPENAI_API_MOCK = '1'
+$env:STRICT_JSON = '1'
+$env:ABSTAIN_ON_NO_EVIDENCE = '1'
+$env:MIN_SCORE = '0.40'
+
+# 2) Optional metrics
+$env:METRICS_DIR = 'artifacts/metrics'
+$env:METRICS_JSONL = '1'
+
+# 3) Ingest free datasets (HTSUS 84, 85 + CROSS + CFR slices)
+python -m app.cli.ingest_cli htsus 84 85
+python -m app.cli.ingest_cli --json cross 8407.10 8501.10
+python -m app.cli.ingest_cli --json cfr 102 177
+
+# 4) Sanity eval (offline golden)
+pytest -q -k "offline_golden or golden_smoke"
+```
+
+**Expected (typical):**
+- HTSUS 84/85: idempotent upserts (hundreds–thousands of chunks depending on chunker config)
+- CROSS/CFR JSON responses printed to console with `"ok": true` (when `--json` used)
+- PyTest: all offline suites pass; no network calls
+
+## 3) Quickstart — Docker parity (offline-first)
+```powershell
+docker build -t dutysavingcopilot:dev .
+docker run --rm `
+  -e NO_NETWORK=1 -e OPENAI_API_MOCK=1 `
+  -e STRICT_JSON=1 -e ABSTAIN_ON_NO_EVIDENCE=1 -e MIN_SCORE=0.40 `
+  -e METRICS_DIR=/work/artifacts/metrics -e METRICS_JSONL=1 `
+  -v ${PWD}:/work `
+  dutysavingcopilot:dev pytest -q -k "offline_golden or golden_smoke"
+```
+
+## 4) Optional pgvector path (manual)
+```powershell
+# Use Session Pooler DSN (e.g., Supabase 6543) or your Postgres
+$env:PG_DSN = 'postgresql+psycopg://<user>:<pass>@<host>:6543/<db>?sslmode=require'
+python -m app.cli.ingest_cli htsus 84 85 --pg
+pytest -q -k "online_smoke"   # only if such test is enabled locally
+```
+> The `--pg` flag (or environment switch if implemented) routes writes to pgvector; otherwise SQLite/dev store is used.
+
+## 5) Metrics & Artifacts
+- JSONL callback is wired in `app/metrics/cb.py` and activated with `METRICS_JSONL=1`.
+- Artifacts live in `artifacts/metrics/*.jsonl` (+ a human summary printed to stdout).
+
+## 6) Troubleshooting
+**Nothing ingests / counts stay 0**
+- Confirm you ran: `python -m app.cli.ingest_cli htsus 84 85`
+- Remove stale dev DB/cache if schema changed; re-run.
+
+**Unexpected network calls offline**
+- Ensure `NO_NETWORK=1` and `OPENAI_API_MOCK=1` are exported in the *same* shell.
+
+**pgvector writes fail**
+- Check `PG_DSN` (or `DATABASE_URL`), SSL params, and port (Supabase Session Pooler is often `6543`).
+- Ensure you created required extensions (`vector`) if not using managed pgvector.
+
+**Non-deterministic evals**
+- Confirm deterministic seeds and fixed chunking settings; avoid parallel ingestion variance.
+
+---
+*Status:* Draft for 15-4. Update after Phase-6 ingestion wiring and CI step-gating land.
+
*** End Patch
