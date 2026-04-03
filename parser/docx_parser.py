"""
Parse a DOCX mock shell using python-docx to extract table text,
then send to GPT-4o-mini for JSON structuring.
"""
import json
import os
import io
from openai import OpenAI
from dotenv import load_dotenv
import docx

load_dotenv()

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


def _extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract all table content and paragraph text from a DOCX file."""
    doc = docx.Document(io.BytesIO(file_bytes))
    lines = []

    # Extract paragraphs (title, footnotes, etc.)
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            lines.append(text)

    # Extract tables
    for table_idx, table in enumerate(doc.tables):
        lines.append(f"\n--- TABLE {table_idx + 1} ---")
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            lines.append(" | ".join(cells))

    return "\n".join(lines)


def parse_docx(file_bytes: bytes, api_key: str | None = None) -> dict:
    """
    Extract text from DOCX and send to GPT-4o-mini for JSON structuring.
    """
    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    extracted_text = _extract_text_from_docx(file_bytes)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Parse this clinical mock shell table (extracted from Word/DOCX) "
                    "into the JSON schema:\n\n" + extracted_text
                ),
            },
        ],
        max_tokens=2000,
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)
