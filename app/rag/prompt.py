# app/rag/prompt.py
from __future__ import annotations

SYSTEM_RULES = """
You are an HTS (Harmonized Tariff Schedule) classification assistant.

OUTPUT FORMAT (MANDATORY)
- Output **only** a single JSON object that conforms to the provided JSON Schema.
- No preamble or trailing prose. No markdown. No explanations outside JSON.

BEHAVIORAL RULES
- Pick 1–3 candidate codes.
- If uncertain, return a single best guess with confidence 0.30–0.49 (do not fabricate certainty).
- Use short, plain-English descriptions.
- Rationale must be specific to the query.
- Evidence:
  - Prefer IDs from the provided context snippets.
  - Use `{"source":"HTS","id":"HTS:NNNN.NN","url":null}` for HTS rows.
  - Use `{"source":"RULING","id":"<ruling id or cite>","url":"<public url>"}` for CBP rulings.
- Never invent HS codes that do not exist.
- Always include this disclaimer exactly once: "Not legal advice. Verify with a licensed customs broker or counsel."
"""


def make_user_prompt(query: str, context: dict) -> str:
    """Render the user message with compact context blocks."""
    hts_lines = []
    for h in (context or {}).get("hts", []):
        # Sample: 8504.40 — Static converters (duty: <value or n/a>)
        duty = h.get("duty_rate") or "n/a"
        hts_lines.append(f"{h.get('code','?')} — {h.get('description','').strip()} (duty: {duty})")

    rule_lines = []
    for r in (context or {}).get("rulings", []):
        # Sample: [0.812] HQ H301619 — https://rulings.cbp.gov/... — "excerpt…"
        rule_lines.append(
            f"[{r.get('hybrid_score',0)}] {r.get('ruling_id','?')} — {r.get('url','')} — {r.get('excerpt','')}"
        )

    hts_block = "\n".join(hts_lines) or "(none)"
    rulings_block = "\n".join(rule_lines) or "(none)"

    return (
        f"QUERY:\n{query}\n\n"
        "CONTEXT — HTS CANDIDATES:\n"
        f"{hts_block}\n\n"
        "CONTEXT — RULING SNIPPETS:\n"
        f"{rulings_block}\n\n"
        "Return ONLY the JSON object (no extra text)."
    )
