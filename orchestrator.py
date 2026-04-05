"""
Orchestrator: generates R code from table JSON + AdaM specs JSON.

Pipeline:
  1. generate_r_recipe()   — LLM produces a structured JSON recipe (no free-form R)
  2. assemble_r_from_recipe() — Python deterministically assembles valid R code from the recipe
  3. fix_r_script()        — if execution fails, LLM fixes the broken code (Option A retry)

This two-step approach prevents Tplyr API misuse by construction:
  - `by` parameter is always a data column name or null (never a string label)
  - One layer per analysis variable (never one layer per category)
  - Package block, load, filters, derived vars are assembled from structured fields
"""

import json
from llm_client import call_llm

# ── Package auto-install block (always prepended to every script) ─────────────
_PACKAGE_BLOCK = r"""# Auto-install required packages (writable user library for restricted environments)
local_lib <- path.expand("~/R/library")
dir.create(local_lib, recursive = TRUE, showWarnings = FALSE)
locks <- list.files(local_lib, pattern = "^00LOCK-", full.names = TRUE)
unlink(locks, recursive = TRUE)
.libPaths(c(local_lib, .libPaths()))

pkgs <- c("Tplyr", "dplyr", "haven", "stringr", "tidyr")
for (pkg in pkgs) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    install.packages(pkg,
      repos        = "https://cloud.r-project.org",
      lib          = local_lib,
      dependencies = c("Depends", "Imports", "LinkingTo"),
      INSTALL_opts = "--no-lock",
      Ncpus        = 1L)
  }
}
library(Tplyr)
library(dplyr)
library(haven)
library(stringr)
library(tidyr)"""

# ── Recipe system prompt ──────────────────────────────────────────────────────
_RECIPE_SYSTEM = """
You are a clinical R/SAS statistical programmer. Given a table shell JSON and AdaM specs,
produce a structured R recipe JSON that describes exactly how to build the table.

RECIPE JSON SCHEMA:
{
  "approach": "tplyr",
  "dataset_var": "<R variable name, e.g. adsl, adae, adrs>",
  "pre_filters": ["<R filter expression, e.g. FASFL == 'Y'">],
  "derived_vars": [
    {
      "dataset_var": "<R variable to mutate>",
      "name": "<new column name>",
      "expr": "<R expression>"
    }
  ],
  "tables": [
    {
      "table_var": "t1",
      "dataset_var": "<R variable name for this table>",
      "treatment_var": "<column name, e.g. TRTP>",
      "add_total": true,
      "layers": [
        {
          "type": "group_desc",
          "var": "<continuous column name>",
          "nested_var": null,
          "by_var": null,
          "distinct_by": null,
          "stats": ["n", "mean", "sd", "median", "min", "max"]
        },
        {
          "type": "group_count",
          "var": "<categorical column name>",
          "nested_var": null,
          "by_var": null,
          "distinct_by": "USUBJID"
        }
      ]
    }
  ],
  "combine_method": "bind_rows"
}

ABSOLUTE RULES — THESE ARE NON-NEGOTIABLE:

1. "by_var" MUST be a data column name (e.g. "RACE") or null.
   NEVER set by_var to a string label like "Best Overall Response" or "Age (Years)".
   String labels are NOT valid Tplyr by_var values and will cause runtime errors.

2. ONE layer per analysis variable.
   NEVER create separate layers for each category of a variable.
   BAD:  8 layers all with var="AVALC" but different string by_var labels
   GOOD: 1 layer with var="AVALC", by_var=null — Tplyr auto-creates one row per unique value

3. AE/SOC-PT tables: var="AEBODSYS", nested_var="AEDECOD", distinct_by="USUBJID"

4. Response/efficacy tables (BOR, ORR, DCR):
   - For AVALC categories: 1 layer, var="AVALC", by_var=null, distinct_by="USUBJID"
   - For derived flags (ORR=CR+PR, DCR=CR+PR+SD): add entry to derived_vars first,
     then use the new derived column name in a separate table's layer

5. Survival/KM tables: set "approach": "survival"

6. Use treatment_variable from AdaM specs (TRTP / TRTA / TRT01P) exactly as specified

7. "combine_method" is "bind_rows" when stacking tables vertically,
   "bind_cols" when merging side-by-side (e.g. severity columns)

8. Output ONLY valid JSON — no markdown fences, no explanation text

9. VARIABLE NAMES MUST EXIST IN THE DATASET — CRITICAL:
   - Every "var", "nested_var", "by_var", "distinct_by" value MUST be a column name
     taken verbatim from the AdaM specs "key_variables" section or the table shell
     "analysis_var" fields.
   - NEVER invent column names. NEVER guess. If a variable is not listed in the AdaM
     specs, DO NOT include a layer for it.
   - If the AdaM specs list AVAL as the numeric analysis variable, use "var": "AVAL" —
     not "Duration_of_Response", not "DOR", not any other invented name.
   - If you are unsure whether a variable exists, omit the layer entirely rather than
     inventing a plausible-sounding name.
"""

# ── QC system prompt ──────────────────────────────────────────────────────────
_QC_SYSTEM = """
You are a senior clinical statistical programming QC reviewer.
You will be given:
  1. A generated R script
  2. The table shell JSON (what the output should look like)
  3. The AdaM specifications JSON (variable names, codelists, conditions)

REVIEW ONLY — CHECK FOR THESE SPECIFIC ISSUES:
  - R syntax errors (unmatched braces, missing commas, wrong function calls)
  - Variable names that do NOT exist in the AdaM specs key_variables
  - final_df not being created or assigned
  - Tplyr API misuse: string passed to by= instead of a data variable name
  - Tplyr API misuse: multiple layers for different categories of the same variable
  - Missing install.packages() lib= parameter (should use local_lib)

DO NOT FLAG THESE — THEY ARE COMMON FALSE POSITIVES:
  - Do NOT flag filter conditions as "wrong" or "missing" if you are unsure.
    The user may have intentionally chosen specific filters. If the AdaM specs
    list population_flags and the script uses them, that is CORRECT — do not
    suggest changing, adding, or removing filter() conditions.
  - Do NOT flag PARAMCD filter choices. The user decides which PARAMCD to use.
  - Do NOT flag treatment variable choice (TRTP vs TRTA) — both are valid.
  - Do NOT suggest cosmetic changes, code style changes, or "improvements"
    that don't fix an actual bug.
  - Do NOT rewrite working code in corrected_code. If you provide corrected_code,
    it MUST be identical to the original except for the specific lines that fix
    the identified ERROR-severity issues.

SEVERITY GUIDELINES:
  - ERROR: Will cause the script to crash (syntax error, missing variable, API misuse)
  - WARNING: Might produce wrong results (e.g. variable not in specs but might exist)
  - INFO: Suggestion only — never auto-correct INFO items

Return a JSON object with this exact schema — no markdown fences:
{
  "qc_passed": true/false,
  "issues": [
    {"severity": "ERROR|WARNING|INFO", "line_hint": "<fragment>", "description": "<what is wrong>"}
  ],
  "corrected_code": "<full corrected R script ONLY if there are ERROR issues, otherwise empty string>"
}

IMPORTANT: Only set qc_passed=false if there are ERROR-severity issues.
WARNING and INFO alone should NOT fail QC.
If there are no ERROR issues: qc_passed=true, corrected_code="".
"""


def _strip_fences(code: str) -> str:
    if code.startswith("```"):
        parts = code.split("```")
        code = parts[1]
        if code.startswith("r\n") or code.startswith("R\n"):
            code = code[2:]
    return code.strip()


# ── Option C: Recipe generation ───────────────────────────────────────────────

def generate_r_recipe(
    table_json: dict,
    adam_specs: dict | None = None,
    api_key: str = "",
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> dict:
    """
    Ask the LLM to produce a structured recipe JSON describing the R table.
    The recipe is then passed to assemble_r_from_recipe() for deterministic code generation.
    """
    adam_section = ""
    if adam_specs:
        adam_section = f"\n\n## AdaM Specifications\n{json.dumps(adam_specs, indent=2)}"

    user_msg = (
        f"## Table Shell JSON\n{json.dumps(table_json, indent=2)}"
        f"{adam_section}\n\n"
        "Produce the R recipe JSON for this table. Output only valid JSON."
    )

    raw = call_llm(
        system=_RECIPE_SYSTEM,
        user=user_msg,
        provider=provider,
        model=model,
        api_key=api_key,
        max_tokens=2000,
    )

    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json\n"):
            raw = raw[5:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Recipe LLM returned invalid JSON.\n\nRaw response:\n{raw[:500]}\n\nError: {e}"
        )


# ── Option C: Deterministic R code assembler ──────────────────────────────────

def assemble_r_from_recipe(recipe: dict) -> str:
    """
    Deterministically assemble a complete R script from a structured recipe dict.
    Always includes the package auto-install block.
    Enforces correct Tplyr API usage by construction.
    """
    dataset_var = recipe.get("dataset_var", "dataset")
    approach    = recipe.get("approach", "tplyr")

    lines = [_PACKAGE_BLOCK, ""]

    # ── Dataset load ──────────────────────────────────────────────────────────
    lines += [
        "ext <- tolower(tools::file_ext(data_path))",
        'if (ext == "sas7bdat") {',
        f'  {dataset_var} <- haven::read_sas(data_path)',
        '} else if (ext == "csv") {',
        f'  {dataset_var} <- read.csv(data_path, stringsAsFactors = FALSE)',
        '} else {',
        '  env <- new.env()',
        '  load(data_path, envir = env)',
        f'  {dataset_var} <- get(ls(env)[1], envir = env)',
        '}',
        '',
    ]

    # ── Pre-filters ───────────────────────────────────────────────────────────
    filters = recipe.get("pre_filters", [])
    if filters:
        filter_expr = ", ".join(filters)
        lines.append(f'{dataset_var} <- {dataset_var} %>% filter({filter_expr})')
        lines.append('')

    # ── Derived vars ──────────────────────────────────────────────────────────
    for dv in recipe.get("derived_vars", []):
        dv_ds = dv.get("dataset_var", dataset_var)
        lines.append(f'{dv_ds} <- {dv_ds} %>% mutate({dv["name"]} = {dv["expr"]})')
    if recipe.get("derived_vars"):
        lines.append('')

    # ── Build tables ──────────────────────────────────────────────────────────
    if approach == "survival":
        lines += _assemble_survival(recipe, dataset_var)
        return '\n'.join(lines)

    table_result_vars = []
    for tbl in recipe.get("tables", []):
        tvar       = tbl.get("table_var", "t1")
        result_var = f"{tvar}_df"
        lines += _assemble_tplyr_table(tbl, result_var)
        lines.append('')
        table_result_vars.append(result_var)

    # ── Combine tables ────────────────────────────────────────────────────────
    combine = recipe.get("combine_method", "bind_rows")
    if not table_result_vars:
        lines.append('final_df <- data.frame()')
    elif len(table_result_vars) == 1:
        lines.append(f'final_df <- {table_result_vars[0]}')
    else:
        args = ', '.join(table_result_vars)
        lines.append(f'final_df <- {combine}({args})')

    return '\n'.join(lines)


def _assemble_tplyr_table(tbl: dict, result_var: str) -> list:
    """Return R code lines for one tplyr_table() → build() call."""
    tbl_dataset  = tbl.get("dataset_var", "dataset")
    treatment_var = tbl.get("treatment_var", "TRTP")
    add_total    = tbl.get("add_total", False)
    layers       = tbl.get("layers", [])
    tvar         = tbl.get("table_var", "t1")

    pipe_parts = [f'tplyr_table({tbl_dataset}, {treatment_var})']
    if add_total:
        pipe_parts.append('  add_total_group()')
    for layer in layers:
        pipe_parts.append(_assemble_layer(layer))

    code = f'{tvar} <- ' + ' %>%\n'.join(pipe_parts)
    return [code, f'{result_var} <- {tvar} %>% build()']


def _assemble_layer(layer: dict) -> str:
    """Return R code snippet for a single add_layer(...) call."""
    layer_type  = layer.get("type", "group_count")
    var         = layer.get("var", "")
    nested_var  = layer.get("nested_var")
    by_var      = layer.get("by_var")   # data column name or null — NEVER a string label
    distinct_by = layer.get("distinct_by")
    stats       = layer.get("stats", [])

    # Variable expression
    var_expr = f"vars({var}, {nested_var})" if nested_var else var
    if by_var:
        var_expr = f"{var_expr}, by = {by_var}"

    parts = []
    if layer_type == "group_desc":
        parts.append(f"    group_desc({var_expr})")
        fmt_items = []
        if "n" in stats:
            fmt_items.append('        "n"         = f_str("xx", n)')
        if "mean" in stats and "sd" in stats:
            fmt_items.append('        "Mean (SD)" = f_str("xx.x (xx.xx)", mean, sd)')
        elif "mean" in stats:
            fmt_items.append('        "Mean"      = f_str("xx.x", mean)')
        if "median" in stats:
            fmt_items.append('        "Median"    = f_str("xx.x", median)')
        if "min" in stats and "max" in stats:
            fmt_items.append('        "Min, Max"  = f_str("xx, xx", min, max)')
        if fmt_items:
            fmt_body = ",\n".join(fmt_items)
            parts.append(f"      set_format_strings(\n{fmt_body}\n      )")
    else:  # group_count
        parts.append(f"    group_count({var_expr})")
        parts.append('      set_format_strings("n (%)" = f_str("xx (xx.x%)", n, pct))')
        if distinct_by:
            parts.append(f"      set_distinct_by({distinct_by})")

    inner = " %>%\n".join(parts)
    return f"  add_layer(\n{inner}\n  )"


def _assemble_survival(recipe: dict, dataset_var: str) -> list:
    """Assemble Kaplan-Meier survival R code."""
    treatment_var = "TRTP"
    if recipe.get("tables"):
        treatment_var = recipe["tables"][0].get("treatment_var", "TRTP")
    return [
        "library(survival)",
        "library(broom)",
        "",
        f"km_fit <- survfit(Surv(AVAL, 1 - CNSR) ~ {treatment_var}, data = {dataset_var})",
        "km_tbl <- summary(km_fit)$table",
        "final_df <- as.data.frame(km_tbl)",
        "final_df$strata <- rownames(final_df)",
        "rownames(final_df) <- NULL",
    ]


# ── Option A: Auto-fix broken R scripts ───────────────────────────────────────

def fix_r_script(
    r_code: str,
    error_log: str,
    table_json: dict,
    adam_specs: dict | None = None,
    api_key: str = "",
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> str:
    """
    Fix a broken R script based on its execution error log.
    Pre-sanitises common convention violations before sending to LLM (Option A).
    """
    # ── Pre-sanitise: strip only bare install.packages() calls that lack lib= ──
    # Keep install.packages() calls that already have lib= (they're correct)
    import re
    def _strip_bare(m):
        return "" if "lib" not in m.group(1) else m.group(0)
    r_code_clean = re.sub(
        r'^\s*install\.packages\s*\(([^)]*)\)\s*$',
        _strip_bare,
        r_code,
        flags=re.MULTILINE,
    )

    # ── Pre-sanitise: ensure the proper package block is present ──────────────
    if "local_lib <- path.expand" not in r_code_clean:
        r_code_clean = _PACKAGE_BLOCK + "\n\n" + r_code_clean

    # ── Pre-sanitise: ensure data_path is used for dataset loading ────────────
    # If the script never references data_path, inject a load block after libraries
    if "data_path" not in r_code_clean:
        dataset_var = (table_json.get("table_metadata") or {}).get("dataset_source", "dataset")
        dataset_var = dataset_var.lower() if dataset_var else "dataset"
        load_block = (
            f'\next <- tolower(tools::file_ext(data_path))\n'
            f'if (ext == "sas7bdat") {{\n'
            f'  {dataset_var} <- haven::read_sas(data_path)\n'
            f'}} else if (ext == "csv") {{\n'
            f'  {dataset_var} <- read.csv(data_path, stringsAsFactors = FALSE)\n'
            f'}} else {{\n'
            f'  env <- new.env(); load(data_path, envir = env)\n'
            f'  {dataset_var} <- get(ls(env)[1], envir = env)\n'
            f'}}\n'
        )
        # Insert after the last library() call
        match = list(re.finditer(r'^library\s*\(.*?\)\s*$', r_code_clean, re.MULTILINE))
        if match:
            insert_pos = match[-1].end()
            r_code_clean = r_code_clean[:insert_pos] + load_block + r_code_clean[insert_pos:]
        else:
            r_code_clean = r_code_clean + load_block

    adam_section = json.dumps(adam_specs, indent=2) if adam_specs else "Not provided."

    user_msg = f"""The following R script failed with this error. Fix it so it runs without errors.

## Error Log
```
{error_log[-3000:]}
```

## R Script (pre-sanitised)
```r
{r_code_clean}
```

## Table Shell JSON
{json.dumps(table_json, indent=2)}

## AdaM Specs
{adam_section}

Rules for the fix:
- Output ONLY the corrected R code — no explanation, no markdown fences
- final_df must be a plain data frame (not a gt, flextable, or other object)
- Use data_path as the dataset path variable — never hardcode a file path
- Never call install.packages() without lib = path.expand("~/R/library")
- The proper package install block using local_lib is already at the top — KEEP IT EXACTLY AS-IS
- For Tplyr: by= must be a data column name or omitted — never a string label
- One group_count/group_desc layer per analysis variable — not one per category
- Do not include file-writing, gt, flextable, knitr, or RTF output code
- CRITICAL: Only use variable names that actually exist in the dataset per the AdaM
  specs. The error "assert_quo_var_present" means a column name in a Tplyr layer
  does not exist in the dataset — remove or correct that layer using the exact column
  name from AdaM specs (e.g. AVAL, AVALC, USUBJID), never an invented name.
- MINIMAL CHANGES ONLY: Fix ONLY what the error log says is broken. Do NOT rewrite
  working code, do NOT remove existing filter() conditions, do NOT remove existing
  PARAMCD or ANL01FL or FASFL filters, do NOT simplify or restructure code that was
  already correct. Your job is a surgical fix of the specific error, not a rewrite.
"""

    raw = call_llm(
        system=(
            "You are an expert R programmer specializing in clinical trial TLFs. "
            "Fix the broken R script and return only the corrected R code. "
            "Make MINIMAL changes — only fix what the error says is broken. "
            "Do NOT remove filter() conditions, do NOT remove install.packages() blocks, "
            "do NOT simplify or restructure working code. Surgical fix only."
        ),
        user=user_msg,
        provider=provider,
        model=model,
        api_key=api_key,
        max_tokens=3000,
    )
    return _strip_fences(raw)


# ── Main entry point (recipe → assemble pipeline) ─────────────────────────────

def generate_r_script(
    table_json: dict,
    skills_md: str,
    adam_specs: dict | None = None,
    api_key: str | None = None,
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> str:
    """
    Generate R script via the recipe → assemble pipeline (Option C).
    Falls back to direct LLM generation if the recipe step fails.
    """
    try:
        recipe = generate_r_recipe(
            table_json=table_json,
            adam_specs=adam_specs,
            api_key=api_key or "",
            provider=provider,
            model=model,
        )
        return assemble_r_from_recipe(recipe)
    except Exception:
        # Fallback: ask LLM to write R code directly (old behaviour)
        return _generate_r_script_direct(
            table_json, skills_md, adam_specs, api_key, provider, model
        )


def _generate_r_script_direct(
    table_json: dict,
    skills_md: str,
    adam_specs: dict | None = None,
    api_key: str | None = None,
    provider: str = "OpenAI",
    model: str = "gpt-4o-mini",
) -> str:
    """Fallback: ask the LLM to write R code directly (no recipe)."""
    _BASE_SYSTEM = """
You are an expert R programmer for clinical trial statistical programming (TLFs).
Generate a complete, executable R script that produces a data frame named `final_df`.

STRICT RULES:
- Output ONLY valid R code — no markdown, no explanation, no fences
- Use the `data_path` variable — it will be injected before execution
- Always include the package auto-install block using ~/R/library and lib= parameter
- Always name the final output object `final_df`
- Do NOT include pharmaRTF, RTF, or any file-writing code
- For Tplyr: `by` parameter must be a data column name — NEVER a string label
- ONE layer per analysis variable — Tplyr auto-creates one row per unique value
- TPLYR CRITICAL: For response tables, use ONE group_count() layer on the response
  variable (e.g. group_count(AVALC)). Never create one layer per response category.
"""
    adam_section = ""
    if adam_specs:
        adam_section = f"\n## AdaM Specifications\n{json.dumps(adam_specs, indent=2)}\n\n---\n"

    user_message = f"""
## Skills Guide (skills.md)
{skills_md}

---

## Table Shell Specification (JSON)
{json.dumps(table_json, indent=2)}

---
{adam_section}
Generate the R script for this table. Output only R code.
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


# ── QC agent (optional, user-triggered) ───────────────────────────────────────

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
```

## Table Shell JSON
{json.dumps(table_json, indent=2)}

## AdaM Specifications JSON
{adam_section}

Review the R script and return the QC JSON.
"""
    raw = call_llm(
        system=_QC_SYSTEM,
        user=user_message,
        provider=provider,
        model=model,
        api_key=api_key or "",
        max_tokens=3000,
    )

    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json\n"):
            raw = raw[5:]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "qc_passed": False,
            "issues": [{"severity": "ERROR", "line_hint": "", "description": f"QC agent returned non-JSON: {raw[:300]}"}],
            "corrected_code": "",
        }
