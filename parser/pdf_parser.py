"""
Parse a PDF mock shell using pdfplumber to extract table text,
then send to the selected LLM for JSON structuring.
"""
import json
import io
import pdfplumber
from llm_client import call_llm
from ._shell_prompt import SHELL_PARSE_SYSTEM


def _extract_text(file_bytes: bytes) -> str:
    lines = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for num, page in enumerate(pdf.pages):
            lines.append(f"\n--- PAGE {num + 1} ---")
            tables = page.extract_tables()
            if tables:
                for i, tbl in enumerate(tables):
                    lines.append(f"\n-- Table {i + 1} --")
                    for row in tbl:
                        if row:
                            lines.append(" | ".join(str(c).strip() if c else "" for c in row))
            else:
                # Fall back to raw text — preserves leading whitespace, which
                # carries SOC > PT indentation cues for the LLM.
                text = page.extract_text()
                if text:
                    lines.append(text)
    return "\n".join(lines)


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def parse_pdf(
    file_bytes: bytes,
    api_key: str | None = None,
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> dict:
    extracted = _extract_text(file_bytes)
    raw = call_llm(
        system=SHELL_PARSE_SYSTEM,
        user=(
            "Parse this clinical mock shell table (extracted from PDF) into the "
            "JSON schema described in your instructions. Pay especially close "
            "attention to row indentation — leading whitespace in the row labels "
            "indicates SOC > PT (or parameter > category) nesting; every indented "
            "row must record its parent_label and an indent_level >= 1. "
            "Return ONLY the JSON object.\n\n"
            + extracted
        ),
        provider=provider,
        model=model,
        api_key=api_key or "",
        max_tokens=4000,
    )
    return json.loads(_strip_fences(raw))
