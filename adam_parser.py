"""
AdaM Specifications Parser
Reads Excel / PDF / DOCX AdaM spec files and returns a structured JSON dict
that the LLM can use alongside the table shell JSON to generate accurate R code.
"""

import io
import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_SYSTEM = """
You are a clinical data standards expert. You will be given raw text extracted from an
AdaM dataset specification document. Your job is to return a structured JSON object
summarising the key programming metadata.

Return ONLY valid JSON — no markdown fences, no explanation.

Output schema:
{
  "dataset": "<dataset name e.g. ADRS>",
  "description": "<one-line description>",
  "population_flags": [{"variable": "FASFL", "condition": "FASFL='Y'", "label": "Full Analysis Set"}],
  "key_variables": [
    {"variable": "PARAMCD", "label": "Parameter Code", "type": "Char", "codelist": ["BOR", "ORR"], "notes": "..."},
    {"variable": "AVALC",   "label": "Analysis Value", "type": "Char", "codelist": ["CR","PR","SD","PD","NE"], "notes": "..."}
  ],
  "treatment_variable": "TRTP",
  "analysis_conditions": [
    {"output": "Tumor Response Table", "paramcd_filter": "BOR", "anl_flag": "ANL01FL='Y'", "primary_var": "AVALC", "derived_condition": "n(%) by AVALC", "r_skill": "group_count"}
  ],
  "codelists": [
    {"codelist": "AVALC", "code": "CR", "decode": "Complete Response"}
  ]
}

If any section is not present in the text, return an empty list [] for that field.
"""


def _call_llm(raw_text: str, api_key: str | None = None) -> dict:
    key    = api_key or os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=key)
    model  = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Truncate to avoid token overflow; specs can be very long
    text = raw_text[:12000]

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": f"Extract AdaM specs JSON from the following text:\n\n{text}"},
        ],
        max_tokens=2000,
        temperature=0,
    )
    raw = resp.choices[0].message.content.strip()
    # Strip fences if present
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json\n") or raw.startswith("JSON\n"):
            raw = raw[5:]
    return json.loads(raw)


# ─────────────────────────────────────────────────────────────────────────────
# Excel parser
# ─────────────────────────────────────────────────────────────────────────────
def _extract_excel_text(file_bytes: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    lines = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        lines.append(f"\n=== Sheet: {sheet_name} ===")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            line  = " | ".join(cells).strip(" |")
            if line:
                lines.append(line)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# PDF parser
# ─────────────────────────────────────────────────────────────────────────────
def _extract_pdf_text(file_bytes: bytes) -> str:
    import pdfplumber
    lines = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.append(text)
            tables = page.extract_tables()
            for tbl in tables:
                for row in tbl:
                    cells = [c or "" for c in row]
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# DOCX parser
# ─────────────────────────────────────────────────────────────────────────────
def _extract_docx_text(file_bytes: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    lines = []
    for para in doc.paragraphs:
        if para.text.strip():
            lines.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            lines.append(" | ".join(cells))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────
def parse_adam_excel(file_bytes: bytes, api_key: str | None = None) -> dict:
    text = _extract_excel_text(file_bytes)
    return _call_llm(text, api_key=api_key)


def parse_adam_pdf(file_bytes: bytes, api_key: str | None = None) -> dict:
    text = _extract_pdf_text(file_bytes)
    return _call_llm(text, api_key=api_key)


def parse_adam_docx(file_bytes: bytes, api_key: str | None = None) -> dict:
    text = _extract_docx_text(file_bytes)
    return _call_llm(text, api_key=api_key)
