"""
Parse a PNG/JPG mock shell image using an LLM vision model.
Returns a structured JSON dict matching the table chunk schema.
"""
import json
from llm_client import call_llm
from ._shell_prompt import SHELL_PARSE_SYSTEM

_USER_TEXT = (
    "Parse this clinical mock shell table image into the JSON schema described "
    "in your instructions. Pay especially close attention to row indentation — "
    "every indented row must record its parent_label and an indent_level >= 1. "
    "Return ONLY the JSON object."
)


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
    mime = "image/png"

    raw = call_llm(
        system=SHELL_PARSE_SYSTEM,
        user=_USER_TEXT,
        provider=provider,
        model=model,
        api_key=api_key or "",
        image_bytes=file_bytes,
        image_mime=mime,
        max_tokens=4000,
    )
    return json.loads(_strip_fences(raw))
