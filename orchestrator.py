"""
Orchestrator: generates R code from table JSON + AdaM specs JSON + skills.md
Also provides a QC agent that reviews the generated code for correctness.
"""

import json
import platform
from llm_client import call_llm

_BASE_SYSTEM = """
You are an expert R programmer for clinical trial statistical programming (TLFs).
You will be given:
  1. A JSON object describing the table structure (parsed mock shell)
  2. An AdaM specifications JSON describing the dataset variables, codelists, and analysis conditions
  3. A skills guide (skills.md) defining the R coding patterns and packages to use
  4. The current deployment environment (Windows or Streamlit Cloud Linux)

Your job is to generate a complete, executable R script that produces
a data frame named `final_df` matching the table structure.

STRICT RULES:
- Output ONLY valid R code — no markdown, no explanation, no fences
- The script must be self-contained and runnable via Rscript
- Use the `data_path` variable — it will be injected before execution
- Always name the final output object `final_df`
- Do NOT include pharmaRTF, RTF, or any file-writing code
- Use the exact variable names from the AdaM specs JSON
- Apply population flags and PARAMCD filters from the AdaM specs JSON
- Choose the correct SKILL(s) from the skills guide based on the table type

DEPLOYMENT RULE:
- If running on Streamlit Cloud (Linux), packages are pre-installed via packages.txt.
  → NEVER include any install.packages() calls or auto-install logic.
  → Only use library() statements.
- On local Windows you may include the auto-install block from SKILL 1.
"""

_QC_SYSTEM = """
You are a senior clinical statistical programming QC reviewer.
... (unchanged - your original QC system prompt) ...
"""   # ← I kept your QC_SYSTEM exactly as you wrote it


def _strip_fences(code: str) -> str:
    if code.startswith("```"):
        parts = code.split("```")
        code = parts[1] if len(parts) > 1 else code
        if code.startswith(("r\n", "R\n")):
            code = code[2:]
    return code.strip()


# ── Main code generator ───────────────────────────────────────────────────────
def generate_r_script(
    table_json: dict,
    skills_md: str,
    adam_specs: dict | None = None,
    api_key: str | None = None,
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> str:
    # Detect environment once
    is_cloud = platform.system() == "Linux"

    deployment_note = (
        "\n**DEPLOYMENT ENVIRONMENT (IMPORTANT):** "
        "This script will run on **Streamlit Cloud (Linux)**. "
        "All required R packages are already pre-installed via packages.txt. "
        "DO NOT include any install.packages() calls or auto-install block. "
        "Just use library(package_name) and assume the packages are available.\n"
        if is_cloud
        else "\n**DEPLOYMENT ENVIRONMENT:** Running locally on Windows. "
             "You may include the package auto-install block from SKILL 1 if desired.\n"
    )

    adam_section = ""
    if adam_specs:
        adam_section = f"\n## AdaM Dataset Specifications (JSON)\n{json.dumps(adam_specs, indent=2)}\n\n---\n"

    user_message = f"""
## Skills Guide (skills.md)
{skills_md}

---{deployment_note}

## Table Shell Specification (JSON)
{json.dumps(table_json, indent=2)}

---
{adam_section}
Generate the R script for this table.
- Use `data_path` as the variable holding the path to the dataset file.
- Apply all population filters and PARAMCD conditions from the AdaM specs.
- Use exact variable names from the AdaM specs.
- Choose the correct SKILL(s) from the guide above.
Output only R code.
"""

    raw = call_llm(
        system=_BASE_SYSTEM,
        user=user_message,
        provider=provider,
        model=model,
        api_key=api_key or "",
        max_tokens=3000,
    )
    return _strip_fences(raw)


# ── QC agent (unchanged) ──────────────────────────────────────────────────────
def qc_r_script(
    r_code: str,
    table_json: dict,
    adam_specs: dict | None = None,
    api_key: str | None = None,
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> dict:
    adam_section = json.dumps(adam_specs, indent=2) if adam_specs else "Not provided."

    user_message = f"""
## R Script to Review
```r
{r_code}