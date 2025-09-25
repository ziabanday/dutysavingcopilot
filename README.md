# HTS Duty-Saving Copilot (Agentic RAG • U.S. Imports)

![MIT License](https://img.shields.io/badge/license-MIT-green.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![FastAPI](https://img.shields.io/badge/web-FastAPI-009688.svg)
![Supabase ready](https://img.shields.io/badge/db-Supabase%20%7C%20pgvector-3ECF8E.svg)

An **Agentic RAG** copilot that helps classify products under the **U.S. HTSUS** and surface **duty-saving** opportunities with grounded citations.  
The agent plans retrieval, chooses among multiple tools (HTSUS, CBP CROSS rulings, Section-301 flags, PGA cross-refs), synthesizes an answer, and **abstains** when evidence is weak.

---

## Features (Week-1 → Week-4 recap)
- **Hybrid retrieval** (BM25 + embeddings) with fusion.
- **Evidence-grounded responses** (citations required) and **abstain** policy.
- **Guardrails** (e.g., `MIN_SCORE=0.40`, strict JSON schema).
- **Eval harness** with canonical metrics & smoke tests.
- **Clean repo hygiene**: `.env.example`, `.gitignore`, CI scaffolding.
- **Week-5a (in progress)**: migrate from SQLite to **Supabase (Postgres + pgvector)** for scalable storage & retrieval.

---

## How it works (Agentic RAG)
1. **Planner/Router** (LLM) decides *whether* to retrieve and *which* tool(s) to call.
2. **Tools**
   - `vector_htsus` (pgvector over HTSUS legal text & notes)
   - `vector_cross` (CBP CROSS rulings)
   - `remedy_301_lookup`
   - `pga_map_lookup` (FDA/APHIS triggers)
   - `bm25_lexical` (lexical recall)
3. **Synthesizer** composes an answer with citations.
4. **Critic** verifies binding authority and confidence. If weak → retry or **abstain**.

---

## Quickstart (Local)

```bash
# 1) Create virtual env (Windows PowerShell shown)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) Install deps
pip install -r requirements.txt

# 3) Create local env
copy .env.example .env

# 4) (Optional) seed tiny offline sample
python app/db/seed_sample.py

# 5) Run API
uvicorn app.api.main:app --reload
