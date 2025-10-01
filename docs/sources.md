*** Begin Patch
*** Add File: docs/sources.md
+# Sources, Coverage & ID Semantics — Free Datasets Pilot (HTSUS 84–85)
+
+## 1) Scope & Coverage
+| Source | Scope in Pilot | Purpose | Update Cadence |
+|---|---|---|---|
+| **HTSUS** | Chapters **84–85** (Machinery / Electrical) | Canonical legal text for classification | Periodic (editions/notes) |
+| **CROSS Rulings** | Rulings cited for 84–85 headings/subheadings | Precedent/interpretation | Continuous |
+| **CFR** | Parts **102** & **177** | Marking rules & ruling procedures | Periodic |
+
+## 2) Stable IDs (document-level)
+- **HTSUS**: `htsus:{chapter}:{heading}[.{subhead}]@{edition}`  
+  e.g., `htsus:84:8407.10@2025-01-01`
+- **CROSS**: `cross:{ruling_number}`  
+  e.g., `cross:NY N012345`
+- **CFR**: `cfr:{title}:{part}[@{edition}]`  
+  e.g., `cfr:19:177@2025-01-01`
+
+> `@{edition}` (date or tag) is included when available to enable **version pinning** and reproducible evals.
+
+## 3) Chunk IDs (passage-level)
+`{doc_id}#p{para}-c{chunk}` or `{doc_id}#s{section}-o{offset}`  
+Examples:
+- `htsus:84:8407.10@2025-01-01#s2-o000120`
+- `cross:NY N012345#p5-c1`
+
+## 4) Versioning Semantics
+- Each ingest writes a **materialized `edition`** for HTSUS/CFR when provided and a **content hash** for invariance checks.
+- Rulings are treated as append-only; corrections bump the `rev` field.
+- Evaluations pin to **(source, id, edition)** triples for determinism.
+
+## 5) Minimal Document Schema (logical)
+```json
+{
+  "doc_id": "htsus:84:8407.10@2025-01-01",
+  "source": "htsus",
+  "title": "8407.10 - Reciprocating internal combustion engines",
+  "edition": "2025-01-01",
+  "url": "https://…",
+  "hash": "sha256:…",
+  "ts_ingested": "2025-10-01T00:00:00Z",
+  "meta": { "chapter": 84, "heading": "8407.10" }
+}
+```
+
+## 6) Minimal Chunk Schema (logical)
+```json
+{
+  "chunk_id": "htsus:84:8407.10@2025-01-01#s2-o000120",
+  "doc_id": "htsus:84:8407.10@2025-01-01",
+  "text": "…",
+  "tokens": 214,
+  "hash": "sha256:…",
+  "meta": { "section": 2, "offset": 120 },
+  "v": null  // pgvector embedding in PROD; null/offlined in SQLite
+}
+```
+
+## 7) Chunking Policy (pilot)
+- Deterministic splitter; fixed window/overlap; headings kept with first child block.
+- Sorted ingestion to enforce stable IDs and reproducible RRF/recall.
+
+## 8) Field Compatibility
+- **SQLite (dev/offline)**: all fields except `v` (vector) are populated.
+- **pgvector (prod/smoke)**: same schema, with `v` set via embedding job; identical IDs.
+
+---
+*Status:* Draft for 15-4. Will be tightened once HTSUS 84–85 loaders and CI gates ship in Phase-6.
+
*** End Patch
