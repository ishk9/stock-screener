"""Canonical Jinja2 templates for the LLM prompts.

Templates are deliberately compact — token cost dominates LLM spend on
large screens. Everything here is rendered with a pre-projected dict;
templates never touch full DataFrames.
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a careful equity analyst for Indian-listed companies. "
    "Reply with VALID JSON ONLY matching the schema. "
    "Never produce numbers; narrate the data given."
)

ANALYSE_TEMPLATE = """\
Company: {{ name }} ({{ symbol }})
Sector: {{ sector or "Unknown" }} | Industry: {{ industry or "Unknown" }}
Market cap bucket: {{ market_cap_bucket or "Unknown" }}
Suggested horizon: {{ horizon }}

Fundamentals (selected):
{%- for k, v in fundamentals.items() %}
- {{ k }}: {{ v }}
{%- endfor %}

Recent returns:
{%- for k, v in returns.items() %}
- {{ k }}: {{ v }}
{%- endfor %}

Top news headlines (last):
{%- for h in headlines %}
- {{ h }}
{%- else %}
- (no recent headlines)
{%- endfor %}

Task: produce a JSON object with these keys:
- thesis_summary (string, <= 2 sentences)
- key_risks (array of <= 5 short strings)
- catalysts (array of <= 5 short strings)
- qualitative_risk (number in 0..1)
- confidence (number in 0..1)
- suggested_horizon (one of "short" | "mid" | "long" | null)

Respond with JSON ONLY. No markdown, no commentary.
"""

__all__ = ["ANALYSE_TEMPLATE", "SYSTEM_PROMPT"]
