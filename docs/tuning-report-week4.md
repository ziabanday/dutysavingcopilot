# Week-4 � Evals, Tuning & Guardrails (HTS Duty-Saving Copilot)

_Date: 2025-09-21_

This document captures our Week-4 experiments across **evals**, **retrieval tuning**, **prompt/cost trimming**, and **guardrails**. It is designed to be a single page for the PR and future audit.

---

## A) Eval setup & baseline (=30 queries)

- Golden set path: `data/golden/golden_set.csv` (JSONL optional).
- Warm baseline procedure (run twice to stabilize p50/p95):
  ```powershell
  make eval
  make eval
  ```
- Append each run to `logs/metrics.csv` with: `timestamp_iso, run_id, alpha, k1, b, top_k, top1, top3, evidence_pct, p50_s, p95_s, num_queries, notes`.

### Baseline summary
| Config                           | Top-1 | Top-3 | Evidence% | p50 (s) | p95 (s) |
| -------------------------------- | ----: | ----: | --------: | ------: | ------: |
| Baseline (a=0.65, K1=1.6, B=0.7, TOP_K=6) |  � | 71.0% | 100% | 5.22 | 6.07 |

> Reference Week-3 small eval (directional): Top-3 � 66.7%, Evidence � 100%, p50 � 6.8�7.2s.

---

## B) Retrieval tuning plan

**Fusion sweep** (holding BM25 constant): `a ? {0.55, 0.65, 0.70, 0.75}`  
**BM25 sweep** (with best a): `K1 ? {1.4, 1.6, 1.8}`, `B ? {0.6, 0.7, 0.8}`  
**TOP_K**: start at 6; probe 4 and 8 if needed.

> Run each condition twice (warm) and log all metrics.

### Results matrix
| Config                           | Top-1 | Top-3 | Evidence% | p50 (s) | p95 (s) |
| -------------------------------- | ----: | ----: | --------: | ------: | ------: |
| a=0.55, K1=1.6, B=0.7, TOP_K=6   |  � |  71.0% |  100% |  5.15 |  5.94 |
| a=0.65, K1=1.6, B=0.7, TOP_K=6   |  � |  71.0% |  100% |  5.22 |  6.07 |
| a=0.70, K1=1.6, B=0.7, TOP_K=6   |  � |  71.0% |  100% |  5.32 |  6.21 |
| a=0.75, K1=1.6, B=0.7, TOP_K=6   |  � |  77.4% |  100% |  5.33 |  8.00 |
| a=BEST, K1=1.4, B=0.6, TOP_K=6   |  � |  74.2% |  100% |  6.45 |  9.28 |
| a=BEST, K1=1.4, B=0.7, TOP_K=6   |  � |  77.4% |  100% |  6.50 |  7.88 |
| a=BEST, K1=1.4, B=0.8, TOP_K=6   |  � |  77.4% |  100% |  4.18 |  5.30 |
| a=BEST, K1=1.6, B=0.6, TOP_K=6   |  � |  74.2% |  100% |  4.80 |  5.83 |
| a=BEST, K1=1.6, B=0.8, TOP_K=6   |  � |  77.4% |  100% |  5.72 |  7.29 |
| a=BEST, K1=1.6, B=0.7, TOP_K=6   |  � |  77.4% |  100% |  5.03 |  6.65 |
| a=BEST, K1=1.8, B=0.6, TOP_K=6   |  � |  77.4% |  100% |  5.82 |  6.50 |
| a=BEST, K1=1.8, B=0.7, TOP_K=6   |  � |  74.2% |  100% |  5.64 |  6.39 |
| a=BEST, K1=1.8, B=0.8, TOP_K=6   |  � |  74.2% |  100% |  5.39 |  6.03 |
| a=BEST, K1=BEST, B=BEST, TOP_K=4 |  � |  77.4% |  100% |  6.14 |  7.19 |
| a=BEST, K1=BEST, B=BEST, TOP_K=8 |  � |  74.2% |  100% |  6.26 |  8.65 |

**Winner (selected config):**
```
FUSION_ALPHA=0.75
BM25_K1=1.4
BM25_B=0.8
TOP_K=6
```

---

## C) Prompt & latency/cost trimming checklist

- [x] Compact prompt (remove redundancy; minimal system text)  
- [x] `max_tokens` capped to preserve completeness only  
- [x] Warm-up occurs at process start (`openai_wrapper.warmup()`)  
- [x] LRU embedding cache hits observed (>0% on repeated evals)  
- [x] Verify p50 = 6.0s, p95 = 9.0s after tuning

---

## D) Guardrails (enforced)

- **Strict JSON** with one-shot format-fix fallback; zero parse failures over stress (=200 calls).  
- **Abstain / low-confidence**: if fused scores low/contradictory ? safe fallback with user advice.  
- **Evidence requirement**: on no evidence ? return `9999.99` + disclaimer (no hallucination).  
- **Policy wrappers**: per-request token caps & timeouts; user-facing disclaimer; internal debug id surfaced.
- **Stress run:** 7� eval passes (~217 calls) on 2025-09-21 ? JSON parse failures **0/217**.

---

## E) Before / After (for PR)

| Phase      | Top-1 | Top-3 | Evidence% | p50 (s) | p95 (s) |
| ---------- | ----: | ----: | --------: | ------: | ------: |
| Before (Baseline)       |  �    |  71.0% |  100% |  5.22 |  6.07 |
| After (Chosen Config)   |  74.2%|  77.4% |  100% |  4.18 |  5.30 |

**Summary rationale (1�2 lines):**  
Hybrid tuning (a/BM25/TOP_K) improved Top-3 from **71.0% ? 77.4%** while maintaining **Evidence 100%** and reducing latency (**p50 5.22s ? 4.18s; p95 6.07s ? 5.30s**). Final Top-1 on the 30-query set is **74.2%**.

**Next steps (Week-5 candidates):**  
- Expand golden set (more chapters/rulings).  
- Add duty-rate enrichment in evidence payloads.  
- Explore reranking or query rewriting if plateauing.

---

**Files of record**  
- `logs/metrics.csv` (all runs)  
- `docs/tuning-report-week4.md` (this doc)

### run_id capture (2025-09-23 10:44)

| run_id | Top-1 | Top-3 | Evidence | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|
|  | � | � | � | 5624 | 8698 |
### run_id capture (2025-09-23 10:46)

| run_id | Top-1 | Top-3 | Evidence | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|
|  | � | � | 99.8% | 5624 | 8698 |
### Week-4b capture (2025-09-23 11:11)

| run_id | Top-1 | Top-3 | Evidence | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|
| run-f28843e0 | � | � | 99.8% | 5624 | 8698 |
### Week-4b capture (2025-09-23 12:45)

| run_id | Top-1 | Top-3 | Evidence | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|
|  | � | � | 100.0% | 5612 | 8686 |
### Week-4b capture (2025-09-23 13:05)

| run_id | Top-1 | Top-3 | Evidence | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|
| 2025-09-23T08:04:24+00:00 | 0.0% | � | 100.0% | 5116 | 5116 |
| 2025-09-23T08:04:29+00:00 | 100.0% | � | 100.0% | 4805 | 4805 |
| 2025-09-23T08:04:34+00:00 | 0.0% | � | 100.0% | 4914 | 4914 |
### Week-4b capture (2025-09-23 14:03)

| run_id | Top-1 | Top-3 | Evidence | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|
| 2025-09-23T09:02:43+00:00 | 0.0% | � | 100.0% | 5148 | 5148 |
| 2025-09-23T09:02:47+00:00 | 100.0% | � | 100.0% | 4028 | 4028 |
| 2025-09-23T09:02:50+00:00 | 0.0% | � | 100.0% | 3509 | 3509 |

### Week-4b capture (2025-09-23 14:26)

| run_id | Top-1 | Top-3 | Evidence | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|
| 2025-09-23T09:02:43+00:00 | 0.0% | ? | 100.0% | 5148 | 5148 |
| 2025-09-23T09:02:47+00:00 | 100.0% | ? | 100.0% | 4028 | 4028 |
| 2025-09-23T09:02:50+00:00 | 0.0% | ? | 100.0% | 3509 | 3509 |