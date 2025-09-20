# HTS Duty-Saving Copilot (MVP Skeleton)

Minimal starter aligned to Phase-1. Week-0/Week-1 focus: guardrails + /health + seed data.

## Quickstart (Windows / Git Bash)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# optional: copy environment template
copy .env.example .env

# seed tiny offline sample
python app/db/seed_sample.py

# run API
uvicorn app.api.main:app --reload
```

Visit http://127.0.0.1:8000/health

## Notes
- This skeleton includes a **token budget guardrail** and structured logging stubs.
- `/classify` currently returns a placeholder response; real RAG wiring comes in Week-2.
