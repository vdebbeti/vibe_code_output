"""
TLF Output Generator — Streamlit App
LLM-as-Compiler: Mock Shell → JSON → AdaM Specs → R Script → QC → final_df

Run with:
    streamlit run app.py
"""

import json
import os
import io
import streamlit as st
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from parser import parse_png, parse_docx, parse_pdf
from adam_parser import parse_adam_excel, parse_adam_pdf, parse_adam_docx
from orchestrator import generate_r_script, qc_r_script
from r_executor import run_r_script

load_dotenv()

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
SKILLS_PATH = BASE_DIR / "skills.md"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TLF Output Generator",
    page_icon="📊",
    layout="wide",
)

# ── Sidebar — API key ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔑 OpenAI API Key")
    _env_key = os.getenv("OPENAI_API_KEY", "")
    _key_input = st.text_input(
        "Paste your OpenAI API key",
        value=_env_key,
        type="password",
        placeholder="sk-...",
        help="Your key is stored only in your browser session and never saved to disk.",
    )
    # Resolve: prefer what the user typed; fall back to .env
    OPENAI_API_KEY = _key_input.strip() or _env_key

    if OPENAI_API_KEY:
        st.success("API key set ✓", icon="✅")
    else:
        st.warning("Enter your OpenAI API key to use the app.", icon="⚠️")

    st.divider()
    st.caption("Key is used only for the current session and never stored on the server.")

st.title("📊 TLF Output Generator")
st.caption(
    "Upload a mock shell → Parse to JSON → Load AdaM Specs → Generate R code → QC Review → Execute → Download"
)

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in {
    "table_json":        None,
    "adam_specs":        None,
    "r_code":            "",
    "qc_result":         None,
    "result_csv_path":   None,
    "run_log":           "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def load_skills() -> str:
    if SKILLS_PATH.exists():
        return SKILLS_PATH.read_text(encoding="utf-8")
    return ""


def _sample_bytes(filename: str) -> bytes | None:
    p = DATA_DIR / filename
    return p.read_bytes() if p.exists() else None


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📄 1 · Parse Shell",
    "📑 2 · AdaM Specs",
    "🛠️ 3 · Skills Editor",
    "💻 4 · Generate & QC",
    "▶️ 5 · Run & Download",
    "ℹ️ Help",
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Parse Shell
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Step 1 · Upload & Parse Mock Shell")

    col_info, col_dl = st.columns([3, 1])
    with col_info:
        st.markdown(
            "Upload a **PNG, JPG, PDF, or DOCX** mock shell. "
            "The LLM extracts columns, rows, statistics, and metadata into a JSON chunk."
        )
    with col_dl:
        sample = _sample_bytes("sample_shell_annotated.png")
        if sample:
            st.download_button(
                label="⬇️ Download sample shell",
                data=sample,
                file_name="sample_shell_annotated.png",
                mime="image/png",
                use_container_width=True,
                help="Annotated oncology efficacy mock shell showing dataset / variable / condition labels",
            )

    uploaded_file = st.file_uploader(
        "Choose a mock shell file",
        type=["png", "jpg", "jpeg", "pdf", "docx"],
        help="Supported: PNG/JPG images, PDF documents, Word DOCX files",
    )

    if uploaded_file:
        st.info(f"File loaded: **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")

        # Show image preview for PNGs
        ext = uploaded_file.name.rsplit(".", 1)[-1].lower()
        if ext in ("png", "jpg", "jpeg"):
            st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)
            uploaded_file.seek(0)

        parse_btn = st.button("🔍 Parse Shell → JSON", type="primary")

        if parse_btn:
            file_bytes = uploaded_file.read()
            if not OPENAI_API_KEY:
                st.error("Enter your OpenAI API key in the sidebar first.")
                st.stop()
            with st.spinner("Sending to GPT-4o-mini for parsing..."):
                try:
                    if ext in ("png", "jpg", "jpeg"):
                        result = parse_png(file_bytes, api_key=OPENAI_API_KEY)
                    elif ext == "docx":
                        result = parse_docx(file_bytes, api_key=OPENAI_API_KEY)
                    elif ext == "pdf":
                        result = parse_pdf(file_bytes, api_key=OPENAI_API_KEY)
                    else:
                        st.error(f"Unsupported file type: .{ext}")
                        result = None

                    if result:
                        st.session_state.table_json = result
                        st.success("Parsing complete! Proceed to Step 2.")
                except Exception as e:
                    st.error(f"Parsing failed: {e}")

    if st.session_state.table_json:
        st.subheader("Extracted JSON")
        st.caption("Review and edit before generating code.")

        json_str = st.text_area(
            "Table JSON",
            value=json.dumps(st.session_state.table_json, indent=2),
            height=380,
            label_visibility="collapsed",
        )
        c1, c2 = st.columns([1, 5])
        with c1:
            if st.button("💾 Save JSON edits"):
                try:
                    st.session_state.table_json = json.loads(json_str)
                    st.success("JSON updated.")
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")

        with st.expander("Parsed structure preview"):
            tj   = st.session_state.table_json
            meta = tj.get("table_metadata", {})
            st.markdown(f"**Title:** {meta.get('title', 'N/A')}")
            st.markdown(f"**Population:** {meta.get('population', 'N/A')}")
            st.markdown(f"**Dataset:** {meta.get('dataset_source', 'N/A')}")
            cols = tj.get("columns", [])
            rows = tj.get("rows", [])
            if cols:
                st.markdown("**Columns:**")
                st.dataframe(pd.DataFrame(cols), use_container_width=True, hide_index=True)
            if rows:
                st.markdown("**Rows:**")
                st.dataframe(
                    pd.DataFrame([{"label": r.get("label"), "analysis_var": r.get("analysis_var"), "stats": ", ".join(r.get("stats", []))} for r in rows]),
                    use_container_width=True, hide_index=True,
                )
    else:
        st.info("Upload a file and click **Parse Shell → JSON** to begin.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — AdaM Specs
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Step 2 · Upload AdaM Specifications")

    col_info2, col_dl2 = st.columns([3, 1])
    with col_info2:
        st.markdown(
            "Upload an **Excel, PDF, or DOCX** AdaM specification file. "
            "The LLM extracts variable names, codelists, population flags, "
            "and analysis conditions — feeding them directly into the code generator."
        )
    with col_dl2:
        sample_specs = _sample_bytes("sample_adam_specs.xlsx")
        if sample_specs:
            st.download_button(
                label="⬇️ Download sample AdaM specs",
                data=sample_specs,
                file_name="sample_adam_specs.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                help="Sample ADRS AdaM specifications with variables, codelists, and analysis conditions",
            )

    adam_file = st.file_uploader(
        "Choose an AdaM spec file",
        type=["xlsx", "xls", "pdf", "docx"],
        help="Supported: Excel (.xlsx/.xls), PDF, Word DOCX",
    )

    if adam_file:
        st.info(f"File loaded: **{adam_file.name}** ({adam_file.size:,} bytes)")
        adam_ext = adam_file.name.rsplit(".", 1)[-1].lower()

        parse_adam_btn = st.button("🔍 Parse AdaM Specs → JSON", type="primary")

        if parse_adam_btn:
            if not OPENAI_API_KEY:
                st.error("Enter your OpenAI API key in the sidebar first.")
                st.stop()
            file_bytes = adam_file.read()
            with st.spinner("Sending to GPT-4o-mini for AdaM spec parsing..."):
                try:
                    if adam_ext in ("xlsx", "xls"):
                        result = parse_adam_excel(file_bytes, api_key=OPENAI_API_KEY)
                    elif adam_ext == "pdf":
                        result = parse_adam_pdf(file_bytes, api_key=OPENAI_API_KEY)
                    elif adam_ext == "docx":
                        result = parse_adam_docx(file_bytes, api_key=OPENAI_API_KEY)
                    else:
                        st.error(f"Unsupported file type: .{adam_ext}")
                        result = None

                    if result:
                        st.session_state.adam_specs = result
                        st.success("AdaM specs parsed! Proceed to Step 3 or jump to Step 4.")
                except Exception as e:
                    st.error(f"AdaM parsing failed: {e}")

    if st.session_state.adam_specs:
        st.subheader("Extracted AdaM Specs JSON")
        st.caption("Review and edit — these feed directly into the R code generator.")

        adam_str = st.text_area(
            "AdaM Specs JSON",
            value=json.dumps(st.session_state.adam_specs, indent=2),
            height=420,
            label_visibility="collapsed",
        )
        c1, _ = st.columns([1, 5])
        with c1:
            if st.button("💾 Save AdaM JSON edits"):
                try:
                    st.session_state.adam_specs = json.loads(adam_str)
                    st.success("AdaM specs updated.")
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")

        with st.expander("AdaM specs summary"):
            specs = st.session_state.adam_specs
            st.markdown(f"**Dataset:** {specs.get('dataset', 'N/A')}")
            st.markdown(f"**Description:** {specs.get('description', 'N/A')}")
            st.markdown(f"**Treatment Variable:** `{specs.get('treatment_variable', 'N/A')}`")
            kv = specs.get("key_variables", [])
            if kv:
                st.markdown("**Key Variables:**")
                st.dataframe(pd.DataFrame(kv), use_container_width=True, hide_index=True)
            ac = specs.get("analysis_conditions", [])
            if ac:
                st.markdown("**Analysis Conditions:**")
                st.dataframe(pd.DataFrame(ac), use_container_width=True, hide_index=True)
    else:
        st.info("Upload an AdaM spec file and click **Parse AdaM Specs → JSON**.")
        st.caption("⚠️ Skipping this step is allowed for MVP — the LLM will rely only on the shell JSON and skills guide.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Skills Editor
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Step 3 · Skills Editor")
    st.markdown(
        "This is the **system prompt** for the LLM — it defines which R packages and patterns "
        "to use for each table type. Edit to add new skills or adjust existing ones."
    )

    skills_content = st.text_area(
        "skills.md content",
        value=load_skills(),
        height=600,
        label_visibility="collapsed",
    )
    c1, _ = st.columns([1, 5])
    with c1:
        if st.button("💾 Save skills.md", type="primary"):
            SKILLS_PATH.write_text(skills_content, encoding="utf-8")
            st.success("skills.md saved.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — Generate & QC
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Step 4 · Generate R Code & QC Review")

    if not st.session_state.table_json:
        st.warning("Complete Step 1 first — parse a mock shell to get the table JSON.")
    else:
        meta = st.session_state.table_json.get("table_metadata", {})
        specs_status = "✅ AdaM specs loaded" if st.session_state.adam_specs else "⚠️ No AdaM specs — LLM will use shell JSON + skills only"
        st.info(
            f"**Table:** {meta.get('title', 'Unknown')} | "
            f"**Dataset:** {meta.get('dataset_source', 'Unknown')} | {specs_status}"
        )

        c1, c2 = st.columns([1, 4])
        with c1:
            gen_btn = st.button("⚡ Generate R Script", type="primary", use_container_width=True)

        if gen_btn:
            if not OPENAI_API_KEY:
                st.error("Enter your OpenAI API key in the sidebar first.")
                st.stop()
            with st.spinner("Calling GPT-4o-mini to generate R code..."):
                try:
                    code = generate_r_script(
                        table_json=st.session_state.table_json,
                        skills_md=load_skills(),
                        adam_specs=st.session_state.adam_specs,
                        api_key=OPENAI_API_KEY,
                    )
                    st.session_state.r_code    = code
                    st.session_state.qc_result = None   # reset previous QC
                    st.success("R script generated! Run QC below.")
                except Exception as e:
                    st.error(f"Code generation failed: {e}")

        if st.session_state.r_code:
            st.subheader("Generated R Script")

            edited_code = st.text_area(
                "R script",
                value=st.session_state.r_code,
                height=420,
                label_visibility="collapsed",
                key="r_code_editor",
            )

            c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
            with c1:
                if st.button("💾 Save edits", use_container_width=True):
                    st.session_state.r_code = edited_code
                    st.session_state.qc_result = None
                    st.success("Code updated.")
            with c2:
                st.download_button(
                    label="⬇️ Download .R",
                    data=edited_code,
                    file_name="generated_table.R",
                    mime="text/plain",
                    use_container_width=True,
                )
            with c3:
                qc_btn = st.button("🔎 Run QC Review", type="secondary", use_container_width=True)

            if qc_btn:
                if not OPENAI_API_KEY:
                    st.error("Enter your OpenAI API key in the sidebar first.")
                    st.stop()
                with st.spinner("QC agent reviewing generated code..."):
                    try:
                        qc = qc_r_script(
                            r_code=edited_code,
                            table_json=st.session_state.table_json,
                            adam_specs=st.session_state.adam_specs,
                            api_key=OPENAI_API_KEY,
                        )
                        st.session_state.qc_result = qc
                    except Exception as e:
                        st.error(f"QC agent failed: {e}")

            # ── QC results panel ──
            if st.session_state.qc_result:
                qc = st.session_state.qc_result
                passed = qc.get("qc_passed", False)
                issues = qc.get("issues", [])
                corrected = qc.get("corrected_code", "")

                if passed:
                    st.success("✅ QC Passed — no issues found.")
                else:
                    st.error(f"❌ QC Failed — {len(issues)} issue(s) found.")

                if issues:
                    with st.expander(f"QC Issues ({len(issues)})", expanded=True):
                        for i, issue in enumerate(issues, 1):
                            sev   = issue.get("severity", "INFO")
                            color = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(sev, "⚪")
                            st.markdown(f"**{color} {sev} #{i}**")
                            if issue.get("line_hint"):
                                st.code(issue["line_hint"], language="r")
                            st.markdown(f"> {issue.get('description', '')}")
                            st.divider()

                if corrected:
                    with st.expander("🔧 QC-Corrected Code", expanded=False):
                        st.code(corrected, language="r")
                        c1, c2 = st.columns([1, 4])
                        with c1:
                            if st.button("✅ Apply corrected code", type="primary"):
                                st.session_state.r_code = corrected
                                st.success("Corrected code applied. You can now run it in Step 5.")
                                st.rerun()
                        with c2:
                            st.download_button(
                                label="⬇️ Download corrected .R",
                                data=corrected,
                                file_name="generated_table_qc.R",
                                mime="text/plain",
                            )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 5 — Run & Download
# ═════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("Step 5 · Run R Script & Download Results")

    if not st.session_state.r_code:
        st.warning("Complete Step 4 first — generate an R script.")
    else:
        qc = st.session_state.qc_result
        if qc and not qc.get("qc_passed", True):
            st.warning("⚠️ QC found issues in the generated code. Consider applying QC corrections in Step 4 first.")

        st.markdown(
            "Upload your dataset file (or enter its path) and click **Run**. "
            "The app injects `data_path` and executes the script locally via Rscript."
        )

        data_file = st.file_uploader(
            "Upload dataset file",
            type=["sas7bdat", "csv", "rdata", "rda"],
            help="Supported: SAS7BDAT, CSV, RData/Rda files",
        )
        st.markdown("**— or enter a direct path —**")
        direct_path = st.text_input(
            "Full path to dataset (if already on this machine)",
            placeholder=r"C:\data\adrs.sas7bdat",
        )

        run_btn = st.button("▶️ Run R Script", type="primary")

        if run_btn:
            resolved_path = ""
            if data_file:
                import tempfile
                suffix = "." + data_file.name.rsplit(".", 1)[-1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(data_file.read())
                    resolved_path = tmp.name
            elif direct_path.strip():
                resolved_path = direct_path.strip()
            else:
                st.error("Please upload a dataset file or enter a file path.")

            if resolved_path:
                with st.spinner("Running Rscript… (may take a minute for package installs)"):
                    success, csv_path, log = run_r_script(st.session_state.r_code, resolved_path)
                    st.session_state.result_csv_path = csv_path if success else None
                    st.session_state.run_log = log

                if success:
                    st.success("R script executed successfully!")
                else:
                    st.error("R script failed. See the execution log below.")

        if st.session_state.run_log:
            with st.expander("Execution log", expanded=not bool(st.session_state.result_csv_path)):
                st.code(st.session_state.run_log, language="bash")

        if st.session_state.result_csv_path and os.path.exists(st.session_state.result_csv_path):
            st.subheader("Result: final_df")
            df = pd.read_csv(st.session_state.result_csv_path)
            st.dataframe(df, use_container_width=True)

            c1, c2 = st.columns([1, 1])
            with c1:
                st.download_button(
                    label="⬇️ Download final_df.csv",
                    data=df.to_csv(index=False),
                    file_name="final_df.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with c2:
                import pickle
                st.download_button(
                    label="⬇️ Download final_df.pkl",
                    data=pickle.dumps(df),
                    file_name="final_df.pkl",
                    mime="application/octet-stream",
                    use_container_width=True,
                )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 6 — Help
# ═════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("How to Use TLF Output Generator")
    st.markdown("""
### Workflow (one table at a time)

| Step | Tab | What you do | What happens |
|------|-----|-------------|--------------|
| 1 | Parse Shell | Upload PNG / PDF / DOCX mock shell | LLM extracts table structure → JSON |
| 2 | AdaM Specs | Upload Excel / PDF / DOCX AdaM specs | LLM extracts variables, codelists, conditions → JSON |
| 3 | Skills Editor | Review / edit skills.md | Defines R packages & coding patterns |
| 4 | Generate & QC | Click Generate, then Run QC | LLM writes R code; QC agent checks it |
| 5 | Run & Download | Upload dataset, click Run | Rscript executes locally → download final_df |

### Sample Files
- **Sample shell** (Tab 1 download): Annotated oncology efficacy mock table showing which ADAM variables and conditions to annotate on your own shells.
- **Sample AdaM specs** (Tab 2 download): ADRS specification Excel with Variables, Analysis Conditions, and Codelists sheets.

### Supported Input Formats
| File | Parser used |
|------|-------------|
| PNG / JPG | GPT-4o-mini Vision API |
| PDF | pdfplumber → text → GPT-4o-mini |
| DOCX | python-docx → text → GPT-4o-mini |
| Excel (.xlsx) | openpyxl → text → GPT-4o-mini |

### QC Agent
The QC agent (Step 4) checks the generated R code for:
- Wrong or invented variable names vs. AdaM specs
- Missing population filters (FASFL, ANL01FL)
- Missing PARAMCD filter
- Wrong treatment variable (TRTP vs TRTA)
- Incorrect Tplyr functions
- R syntax issues

If issues are found, a corrected script is offered — click **Apply corrected code** before running.

### Notes
- The app never sends your real data to the LLM — only the shell structure and specs.
- R packages (Tplyr, dplyr, haven, etc.) are auto-installed on first run.
- Rscript must be installed and accessible (detected automatically from `C:/Program Files/R/`).
""")
