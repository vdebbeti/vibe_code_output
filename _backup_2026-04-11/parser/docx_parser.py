"""
Parse a DOCX mock shell using python-docx to extract table text,
then send to the selected LLM for JSON structuring.
"""
import json
import io
import docx
from llm_client import call_llm

_SYSTEM_PROMPT = """
You are a clinical trial table parser. You will receive raw text extracted from a
Word document mock shell (a template table used in clinical study reports).
Convert it into a structured JSON object — no markdown, no explanation.

The JSON must follow this exact schema:
{
  "table_metadata": {
    "title": "<full table title>",
    "population": "<population label if visible, else null>",
    "dataset_source": "<likely ADAM dataset: ADSL, ADAE, ADCM, ADLB, etc.>"
  },
  "columns": [
    {"label": "<column header text>", "type": "<stub|treatment_group|total|subgroup>", "value": "<treatment code or null>"}
  ],
  "rows": [
    {"label": "<row label>", "analysis_var": "<likely SAS/R variable name>", "stats": ["<stat1>", "<stat2>"]}
  ]
}

Rules:
- "type": "stub" for leftmost label column, "treatment_group" for each arm,
  "total" for Total column, "subgroup" for severity/sub-columns.
- "analysis_var": infer the CDISC ADAM variable name (AGE, SEX, RACE, AEBODSYS, AEDECOD, etc.)
- "stats": list statistics shown (e.g. "n", "Mean (SD)", "Median", "Min, Max", "n (%)")
- Return ONLY the JSON object. No markdown fences.
"""


def _extract_text(file_bytes: bytes) -> str:
    doc = docx.Document(io.BytesIO(file_bytes))
    lines = []
    for para in doc.paragraphs:
        if para.text.strip():
            lines.append(para.text)
    for idx, table in enumerate(doc.tables):
        lines.append(f"\n--- TABLE {idx + 1} ---")
        for row in table.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(lines)


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def parse_docx(
    file_bytes: bytes,
    api_key: str | None = None,
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> dict:
    extracted = _extract_text(file_bytes)
    raw = call_llm(
        system=_SYSTEM_PROMPT,
        user=(
            "Parse this clinical mock shell table (extracted from Word/DOCX) "
            "into the JSON schema:\n\n" + extracted
        ),
        provider=provider,
        model=model,
        api_key=api_key or "",
        max_tokens=2000,
    )
    return json.loads(_strip_fences(raw))
