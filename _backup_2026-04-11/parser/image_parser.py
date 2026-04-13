"""
Parse a PNG/JPG mock shell image using an LLM vision model.
Returns a structured JSON dict matching the table chunk schema.
"""
import json
from llm_client import call_llm

_SYSTEM_PROMPT = """
You are a clinical trial table parser. You will receive an image of a mock shell
(a template table used in clinical study reports). Extract its structure and return
ONLY a valid JSON object — no markdown, no explanation.

The JSON must follow this exact schema:
{
  "table_metadata": {
    "title": "<full table title from the image>",
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
- For "type": use "stub" for the leftmost label column, "treatment_group" for each treatment arm,
  "total" for any Total column, "subgroup" for severity/sub-columns.
- For "analysis_var": infer the CDISC ADAM variable name (e.g. AGE, SEX, RACE, AEBODSYS, AEDECOD).
- For "stats": list the statistics shown (e.g. "n", "Mean (SD)", "Median", "Min, Max", "n (%)").
- If rows have a hierarchy (e.g. SOC → PT), represent each as a separate row with the parent label
  indicated by indentation context.
- Return ONLY the JSON object. No markdown fences.
"""

_USER_TEXT = "Parse this clinical mock shell table image into the JSON schema."


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def parse_png(
    file_bytes: bytes,
    api_key: str | None = None,
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> dict:
    """Send image bytes to the selected LLM vision model and return parsed JSON dict."""
    import mimetypes
    mime = "image/png"

    raw = call_llm(
        system=_SYSTEM_PROMPT,
        user=_USER_TEXT,
        provider=provider,
        model=model,
        api_key=api_key or "",
        image_bytes=file_bytes,
        image_mime=mime,
        max_tokens=2000,
    )
    return json.loads(_strip_fences(raw))
