PY := ./.venv/Scripts/python.exe

.PHONY: reindex ingest-hts ingest-rulings ingest-hts-noembed ingest-rulings-noembed setup-dirs eval eval-k1 stress print-config serve

reindex:
	$(PY) -m app.rag.reindex --bm25 --vectors

ingest-hts:
	$(PY) -m app.ingest.hts

ingest-hts-noembed:
	$(PY) -m app.ingest.hts --no-embed

ingest-rulings:
	$(PY) -m app.ingest.rulings --ids-file data/rulings/ids.txt

ingest-rulings-noembed:
	$(PY) -m app.ingest.rulings --ids-file data/rulings/ids.txt --no-embed

setup-dirs:
	$(PY) -c "import os; [os.makedirs(p, exist_ok=True) for p in ['data/hts','data/rulings/raw','data/rulings/normalized','data/index','logs']]"

# Default eval at k=3 (winner config is read from .env via app.config.Settings)
eval:
	$(PY) -m app.rag.eval_golden --k 3 --write-metrics logs/metrics.csv

# Convenience: Top-1 check (k=1)
eval-k1:
	$(PY) -m app.rag.eval_golden --k 1 --write-metrics logs/metrics.csv

# Convenience: ~217 calls (7 passes) to check JSON stability
stress:
	$(PY) -m app.rag.eval_golden --k 3 --write-metrics logs/metrics.csv
	$(PY) -m app.rag.eval_golden --k 3 --write-metrics logs/metrics.csv
	$(PY) -m app.rag.eval_golden --k 3 --write-metrics logs/metrics.csv
	$(PY) -m app.rag.eval_golden --k 3 --write-metrics logs/metrics.csv
	$(PY) -m app.rag.eval_golden --k 3 --write-metrics logs/metrics.csv
	$(PY) -m app.rag.eval_golden --k 3 --write-metrics logs/metrics.csv
	$(PY) -m app.rag.eval_golden --k 3 --write-metrics logs/metrics.csv

# Print the config actually loaded at runtime
print-config:
	$(PY) -c "from app.config import settings; print({'FUSION_ALPHA':settings.FUSION_ALPHA,'BM25_K1':settings.BM25_K1,'BM25_B':settings.BM25_B,'TOP_K':settings.TOP_K,'STRICT_JSON':settings.STRICT_JSON,'ABSTAIN_ON_NO_EVIDENCE':settings.ABSTAIN_ON_NO_EVIDENCE,'MAX_TOKENS':settings.MAX_TOKENS,'TIMEOUT_S':settings.TIMEOUT_S,'WARMUP':settings.WARMUP})"

# Run API locally
serve:
	$(PY) -m uvicorn app.api.main:app --port 8000
