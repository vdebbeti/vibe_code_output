"""
Clinical Table Compiler — Streamlit App
LLM-as-Compiler: Mock Shell → JSON → R Script → final_df

Run with:
    streamlit run app.py
"""
import json
import os
import io
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from parser import parse_png, parse_docx, parse_pdf
from orchestrator import generate_r_script
from r_executor import run_r_script

load_dotenv()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Clinical Table Compiler",
    page_icon="🧬",
    layout="wide",
)

st.title("🧬 Clinical Table Compiler")
st.caption(
    "Upload a mock shell → Parse to JSON → Generate R code → Execute → Download results"
)

# ── Session state defaults ────────────────────────────────────────────────────
if "table_json" not in st.session_state:
    st.session_state.table_json = None
if "r_code" not in st.session_state:
    st.session_state.r_code = ""
if "result_csv_path" not in st.session_state:
    st.session_state.result_csv_path = None
if "run_log" not in st.session_state:
    st.session_state.run_log = ""

# ── Skills.md loader ─────────────────────────────────────────────────────────
SKILLS_PATH = os.path.join(os.path.dirname(__file__), "skills.md")

def load_skills() -> str:
    if os.path.exists(SKILLS_PATH):
        with open(SKILLS_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return ""

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📄 1 · Parse Shell",
    "🛠️ 2 · Skills Editor",
    "💻 3 · Generate R Code",
    "▶️ 4 · Run & Download",
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Parse Shell
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Upload Mock Shell")
    st.markdown(
        "Upload a **PNG, JPG, PDF, or DOCX** file of your clinical table mock shell. "
        "The LLM will extract its structure into a JSON chunk."
    )

    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["png", "jpg", "jpeg", "pdf", "docx"],
        help="Supported: PNG/JPG images, PDF documents, Word DOCX files",
    )

    if uploaded_file:
        st.info(f"File loaded: **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")

        col1, col2 = st.columns([1, 2])
        with col1:
            parse_btn = st.button("🔍 Parse Shell → JSON", type="primary", use_container_width=True)

        if parse_btn:
            file_bytes = uploaded_file.read()
            ext = uploaded_file.name.rsplit(".", 1)[-1].lower()

            with st.spinner("Sending to GPT-4o-mini for parsing..."):
                try:
                    if ext in ("png", "jpg", "jpeg"):
                        result = parse_png(file_bytes)
                    elif ext == "docx":
                        result = parse_docx(file_bytes)
                    elif ext == "pdf":
                        result = parse_pdf(file_bytes)
                    else:
                        st.error(f"Unsupported file type: .{ext}")
                        result = None

                    if result:
                        st.session_state.table_json = result
                        st.success("Parsing complete!")
                except Exception as e:
                    st.error(f"Parsing failed: {e}")

    # Show and allow editing of the JSON
    if st.session_state.table_json:
        st.subheader("Extracted JSON")
        st.caption("Review and edit the JSON before generating R code. Changes here affect code generation.")

        json_str = st.text_area(
            "Table JSON",
            value=json.dumps(st.session_state.table_json, indent=2),
            height=400,
            label_visibility="collapsed",
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("💾 Save JSON edits", use_container_width=True):
                try:
                    st.session_state.table_json = json.loads(json_str)
                    st.success("JSON updated.")
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")

        # Preview parsed structure
        with st.expander("Parsed structure preview"):
            tj = st.session_state.table_json
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
                rows_display = [
                    {
                        "label": r.get("label"),
                        "analysis_var": r.get("analysis_var"),
                        "stats": ", ".join(r.get("stats", [])),
                    }
                    for r in rows
                ]
                st.dataframe(pd.DataFrame(rows_display), use_container_width=True, hide_index=True)
    else:
        st.info("Upload a file and click **Parse Shell → JSON** to begin.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Skills Editor
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Skills Editor")
    st.markdown(
        "This is the **system prompt** for the LLM. It defines which R packages and patterns "
        "to use for each table type. Edit to add new skills or adjust existing ones."
    )

    skills_content = st.text_area(
        "skills.md content",
        value=load_skills(),
        height=600,
        label_visibility="collapsed",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 Save skills.md", type="primary", use_container_width=True):
            with open(SKILLS_PATH, "w", encoding="utf-8") as f:
                f.write(skills_content)
            st.success("skills.md saved.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Generate R Code
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Generate R Code")

    if not st.session_state.table_json:
        st.warning("Complete Step 1 first — parse a mock shell to get the JSON.")
    else:
        meta = st.session_state.table_json.get("table_metadata", {})
        st.info(
            f"Table: **{meta.get('title', 'Unknown')}** | "
            f"Dataset: **{meta.get('dataset_source', 'Unknown')}**"
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            gen_btn = st.button("⚡ Generate R Script", type="primary", use_container_width=True)

        if gen_btn:
            skills_md = load_skills()
            with st.spinner("Calling GPT-4o-mini to generate R code..."):
                try:
                    code = generate_r_script(st.session_state.table_json, skills_md)
                    st.session_state.r_code = code
                    st.success("R script generated!")
                except Exception as e:
                    st.error(f"Code generation failed: {e}")

        if st.session_state.r_code:
            st.subheader("Generated R Script")
            st.caption("Review and edit the code before executing. The app will inject `data_path` automatically.")

            edited_code = st.text_area(
                "R script",
                value=st.session_state.r_code,
                height=500,
                label_visibility="collapsed",
            )

            col1, col2, col3 = st.columns([1, 1, 4])
            with col1:
                if st.button("💾 Save edits", use_container_width=True):
                    st.session_state.r_code = edited_code
                    st.success("Code updated.")
            with col2:
                st.download_button(
                    label="⬇️ Download .R",
                    data=edited_code,
                    file_name="generated_table.R",
                    mime="text/plain",
                    use_container_width=True,
                )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — Run & Download
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Run R Script & Download Results")

    if not st.session_state.r_code:
        st.warning("Complete Step 3 first — generate or paste an R script.")
    else:
        st.markdown(
            "Upload your dataset file and click **Run**. "
            "The app will inject `data_path` into the script and execute it locally via Rscript."
        )

        data_file = st.file_uploader(
            "Upload dataset file",
            type=["sas7bdat", "csv", "rdata", "rda"],
            help="Supported: SAS7BDAT, CSV, RData/Rda files",
        )

        # Alternatively, enter a direct path
        st.markdown("**— or —**")
        direct_path = st.text_input(
            "Enter full path to dataset (if already on this machine)",
            placeholder=r"C:\data\adsl.sas7bdat",
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            run_btn = st.button("▶️ Run R Script", type="primary", use_container_width=True)

        if run_btn:
            # Determine data path
            resolved_path = ""
            if data_file:
                # Save uploaded file to temp location
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
                with st.spinner("Running Rscript... (this may take a minute for package installs)"):
                    success, csv_path, log = run_r_script(
                        st.session_state.r_code,
                        resolved_path,
                    )
                    st.session_state.result_csv_path = csv_path if success else None
                    st.session_state.run_log = log

                if success:
                    st.success("R script executed successfully!")
                else:
                    st.error("R script failed. See the log below.")

        # Show log
        if st.session_state.run_log:
            with st.expander("Execution log", expanded=not bool(st.session_state.result_csv_path)):
                st.code(st.session_state.run_log, language="bash")

        # Show result and download
        if st.session_state.result_csv_path and os.path.exists(st.session_state.result_csv_path):
            st.subheader("Result: final_df")
            df = pd.read_csv(st.session_state.result_csv_path)
            st.dataframe(df, use_container_width=True)

            col1, col2 = st.columns([1, 1])
            with col1:
                st.download_button(
                    label="⬇️ Download final_df.csv",
                    data=df.to_csv(index=False),
                    file_name="final_df.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
