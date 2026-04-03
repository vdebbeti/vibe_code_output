"""
Orchestrator: generates R code from table JSON + AdaM specs JSON + skills.md
Also provides a QC agent that reviews the generated code for correctness.
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_BASE_SYSTEM = """
You are an expert R programmer for clinical trial statistical programming (TLFs).
You will be given:
  1. A JSON object describing the table structure (parsed mock shell)
  2. An AdaM specifications JSON describing the dataset variables, codelists, and analysis conditions
  3. A skills guide (skills.md) defining the R coding patterns and packages to use

Your job is to generate a complete, executable R script that produces
a data frame named `final_df` matching the table structure.

STRICT RULES:
- Output ONLY valid R code — no markdown, no explanation, no fences
- The script must be self-contained and runnable via Rscript
- Use the `data_path` variable — it will be injected before execution
- Always include the package auto-install block (SKILL 1 from skills guide)
- Always name the final output object `final_df`
- Do NOT include pharmaRTF, RTF, or any file-writing code
- Use the exact variable names from the AdaM specs JSON (analysis_var, treatment_variable)
- Apply population flags from the AdaM specs JSON (e.g. FASFL='Y')
- Apply PARAMCD filter from analysis_conditions in the AdaM specs JSON
- Choose the correct SKILL(s) from the guide based on the table type
"""

_QC_SYSTEM = """
You are a senior clinical statistical programming QC reviewer.
You will be given:
  1. A generated R script
  2. The table shell JSON (what the output should look like)
  3. The AdaM specifications JSON (variable names, codelists, conditions)

Your job is to review the R script and identify any issues. Check for:
  - Incorrect or invented variable names (must match AdaM specs exactly)
  - Missing population flag filters (e.g. FASFL='Y', ANL01FL='Y')
  - Missing or wrong PARAMCD filter
  - Wrong treatment variable (TRTP vs TRTA vs TRT01P)
  - Wrong Tplyr function (group_desc vs group_count)
  - Missing add_total_group() when a Total column is specified
  - Missing set_distinct_by(USUBJID) for AE tables
  - final_df not being created or not being a flat data frame
  - Any R syntax errors you can spot

Return a JSON object with this exact schema — no markdown fences:
{
  "qc_passed": true/false,
  "issues": [
    {"severity": "ERROR|WARNING|INFO", "line_hint": "<fragment of code near the issue>", "description": "<what is wrong and how to fix it>"}
  ],
  "corrected_code": "<full corrected R script, or empty string if no corrections needed>"
}

If there are no issues, return qc_passed=true, issues=[], corrected_code="".
"""


def _get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _strip_fences(code: str) -> str:
    if code.startswith("```"):
        parts = code.split("```")
        code = parts[1]
        if code.startswith("r\n") or code.startswith("R\n"):
            code = code[2:]
    return code.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Main code generator
# ─────────────────────────────────────────────────────────────────────────────
def generate_r_script(
    table_json: dict,
    skills_md: str,
    adam_specs: dict | None = None,
) -> str:
    """
    Call GPT-4o-mini with table JSON + AdaM specs + skills.md to generate R code.

    Args:
        table_json:  Parsed table structure dict (from mock shell)
        skills_md:   Content of skills.md
        adam_specs:  Parsed AdaM specifications dict (may be None for MVP fallback)

    Returns:
        R script as a string
    """
    client = _get_client()
    model  = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    adam_section = ""
    if adam_specs:
        adam_section = f"""
## AdaM Dataset Specifications (JSON)
{json.dumps(adam_specs, indent=2)}

---
"""

    user_message = f"""
## Skills Guide (skills.md)
{skills_md}

---

## Table Shell Specification (JSON)
{json.dumps(table_json, indent=2)}

---
{adam_section}
Generate the R script for this table.
- Use `data_path` as the variable holding the path to the dataset file.
- Apply all population filters and PARAMCD conditions from the AdaM specs.
- Use exact variable names from the AdaM specs key_variables section.
- Choose the correct SKILL(s) from the guide above.
Output only R code.
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _BASE_SYSTEM},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=3000,
        temperature=0,
    )

    return _strip_fences(response.choices[0].message.content)


# ─────────────────────────────────────────────────────────────────────────────
# QC agent
# ─────────────────────────────────────────────────────────────────────────────
def qc_r_script(
    r_code: str,
    table_json: dict,
    adam_specs: dict | None = None,
) -> dict:
    """
    Run a QC LLM agent on the generated R script.

    Returns:
        {
            "qc_passed": bool,
            "issues": [{"severity", "line_hint", "description"}],
            "corrected_code": str   # non-empty only when corrections were made
        }
    """
    client = _get_client()
    model  = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    adam_section = json.dumps(adam_specs, indent=2) if adam_specs else "Not provided."

    user_message = f"""
## R Script to Review
```r
{r_code}
```

## Table Shell JSON
{json.dumps(table_json, indent=2)}

## AdaM Specifications JSON
{adam_section}

Review the R script and return the QC JSON.
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _QC_SYSTEM},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=3000,
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    # Strip fences if model adds them
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json\n"):
            raw = raw[5:]

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "qc_passed": False,
            "issues": [{"severity": "ERROR", "line_hint": "", "description": f"QC agent returned non-JSON response: {raw[:300]}"}],
            "corrected_code": "",
        }

    return result
