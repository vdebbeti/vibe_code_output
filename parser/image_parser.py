"""
Parse a PNG/JPG mock shell image using GPT-4o-mini vision.
Returns a structured JSON dict matching the table chunk schema.
"""
import base64
import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

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


def parse_png(file_bytes: bytes, api_key: str | None = None) -> dict:
    """
    Send PNG bytes to GPT-4o-mini vision and return parsed JSON dict.
    """
    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    b64 = base64.b64encode(file_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": "Parse this clinical mock shell table image into the JSON schema.",
                    },
                ],
            },
        ],
        max_tokens=2000,
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown fences if the model adds them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)
