# HTS Duty-Saving Copilot

[Badges: MIT License, Python 3.11, FastAPI, Supabase-ready]

## Overview
Short paragraph describing:
- Purpose: AI agent to classify U.S. HTS codes and suggest duty-saving opportunities
- Based on Agentic RAG (LLM + retrieval agents)
- U.S.-jurisdiction datasets only (CROSS rulings, HTS codes, tariff schedules, etc.)

## Quickstart (Local)
1. Clone repo & create virtual env
2. pip install -r requirements.txt
3. cp .env.example .env
4. uvicorn app.api.main:app --reload

Visit http://127.0.0.1:8000/health

## Docker/Container
```bash
docker build -t hts-copilot .
docker run -p 8000:8000 hts-copilot
