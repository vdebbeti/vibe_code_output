"""
Orchestrator: takes a JSON table chunk + skills.md content
and calls GPT-4o-mini to generate an executable R script.
"""
import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_BASE_SYSTEM = """
You are an expert R programmer for clinical trial statistical programming.
You will be given:
1. A JSON object describing a clinical table structure (mock shell)
2. A skills guide (skills.md) defining the R coding patterns to use

Your job is to generate a complete, executable R script that produces
a data frame named `final_df` matching the table structure.

STRICT RULES:
- Output ONLY valid R code — no markdown, no explanation, no fences
- The script must be self-contained and runnable via Rscript
- Use the `data_path` variable (it will be injected before execution)
- Always include the package auto-install block from SKILL 1
- Always name the final output `final_df`
- Do NOT include pharmaRTF, RTF, or any file-writing code
- Choose the correct SKILL from the guide based on the table type
"""


def generate_r_script(table_json: dict, skills_md: str, data_path_placeholder: str = "data_path") -> str:
    """
    Call GPT-4o-mini with the table JSON + skills.md to generate R code.

    Args:
        table_json: Parsed table structure dict
        skills_md: Content of skills.md
        data_path_placeholder: Variable name for data path (injected at runtime)

    Returns:
        R script as a string
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    table_json_str = json.dumps(table_json, indent=2)

    user_message = f"""
## Skills Guide (skills.md)
{skills_md}

---

## Table Specification (JSON)
{table_json_str}

---

Generate the R script for this table. Use `data_path` as the variable holding
the path to the dataset file. Choose the correct SKILL(s) from the guide above.
Output only R code.
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _BASE_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        max_tokens=3000,
        temperature=0,
    )

    code = response.choices[0].message.content.strip()

    # Strip markdown fences if model adds them
    if code.startswith("```"):
        parts = code.split("```")
        # Take the content between first pair of fences
        code = parts[1]
        if code.startswith("r\n") or code.startswith("R\n"):
            code = code[2:]

    return code
