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
from llm_client import PROVIDER_MODELS, PROVIDER_KEY_LABELS, PROVIDER_KEY_PLACEHOLDERS, PROVIDER_KEY_HELP

load_dotenv()

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
SKILLS_PATH = BASE_DIR / "skills.md"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TLF Output Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Card-style containers */
.block-container { padding-top: 1.5rem; }
div[data-testid="stExpander"] { border-radius: 10px; border: 1px solid rgba(255,255,255,0.08); }

/* Tab styling */
button[data-baseweb="tab"] { font-size: 13px; font-weight: 600; }
button[data-baseweb="tab"][aria-selected="true"] { color: #4fc3f7; }

/* Section headers */
h2 { font-size: 1.25rem !important; font-weight: 700 !important; }
h3 { font-size: 1.05rem !important; }

/* Sidebar */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0d1b2a 0%, #1b2838 100%); }
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label { color: #90caf9 !important; font-weight: 600 !important; font-size: 12px !important; }

/* Success / error / warning boxes */
div[data-testid="stSuccessMessage"] { border-left: 4px solid #66bb6a; }
div[data-testid="stErrorMessage"]   { border-left: 4px solid #ef5350; }
div[data-testid="stWarningMessage"] { border-left: 4px solid #ffa726; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🤖 AI Provider & Model")

    provider = st.selectbox(
        "Provider",
        list(PROVIDER_MODELS.keys()),
        index=0,
        help="Choose which AI provider to use for all LLM calls.",
    )

    model = st.selectbox(
        "Model",
        PROVIDER_MODELS[provider],
        index=0,
        help="Model to use within the selected provider.",
    )

    _env_key = os.getenv("OPENAI_API_KEY", "")
    _key_input = st.text_input(
        PROVIDER_KEY_LABELS[provider],
        value=_env_key if provider == "OpenAI" else "",
        type="password",
        placeholder=PROVIDER_KEY_PLACEHOLDERS[provider],
        help=PROVIDER_KEY_HELP[provider],
    )
    API_KEY = _key_input.strip()

    if API_KEY:
        st.success("API key set ✓", icon="✅")
    else:
        st.warning("Enter your API key to use the app.", icon="⚠️")

    # ── API key tip ───────────────────────────────────────────────────────────
    if provider == "OpenAI":
        st.info(
            "**Tip:** Both `sk-` and `sk-proj-` keys work. "
            "If you get *invalid_api_key*, re-copy carefully — a trailing period or "
            "extra space will break the key.",
            icon="💡",
        )

    st.divider()

    # ── Pipeline status ───────────────────────────────────────────────────────
    st.markdown("### 📋 Pipeline Status")
    ss = st.session_state

    def _badge(cond, label):
        icon = "✅" if cond else "⬜"
        st.markdown(f"{icon} {label}")

    _badge(ss.get("table_json"),   "Shell parsed → JSON")
    _badge(ss.get("adam_specs"),   "AdaM specs loaded")
    _badge(ss.get("r_code"),       "R script generated")

    qc = ss.get("qc_result")
    if qc is None:
        st.markdown("⬜ QC not run")
    elif qc.get("qc_passed"):
        st.markdown("✅ QC passed")
    else:
        n = len(qc.get("issues", []))
        st.markdown(f"❌ QC: {n} issue(s)")

    _badge(ss.get("result_csv_path"), "Results downloaded")

    st.divider()
    st.caption("Your data never leaves your machine — only table structure and specs are sent to the LLM.")


# ── Title & flowchart ─────────────────────────────────────────────────────────
st.html(
    "<h1 style='margin-bottom: 4px;'>📊 TLF Output Generator</h1>"
    "<p style='color: #90a4ae; margin-top: 0; font-size: 14px;'>"
    "LLM-as-Compiler · Mock Shell → JSON → AdaM Specs → R Code → QC → final_df</p>"
)

st.html("""
<div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d2137 100%);
            padding: 22px 20px; border-radius: 14px; margin: 8px 0 24px 0;
            box-shadow: 0 4px 24px rgba(0,0,0,0.4);">
  <p style="color:rgba(255,255,255,0.55); text-align:center; font-size:11px;
             margin:0 0 14px 0; text-transform:uppercase; letter-spacing:1.8px;">
    Workflow Pipeline
  </p>
  <div style="display:flex; align-items:stretch; justify-content:center; gap:0; flex-wrap:nowrap;">

    <div style="background:rgba(99,179,237,0.12); border:1px solid rgba(99,179,237,0.35);
                padding:14px 10px; border-radius:10px; text-align:center; flex:1; min-width:80px;">
      <div style="font-size:26px; margin-bottom:5px;">📄</div>
      <div style="color:#63b3ed; font-weight:700; font-size:11px; margin-bottom:2px;">STEP 1</div>
      <div style="color:#fff; font-size:12px; font-weight:600;">Upload Shell</div>
      <div style="color:rgba(255,255,255,0.45); font-size:10px; margin-top:3px;">PNG · PDF · DOCX</div>
    </div>

    <div style="display:flex; align-items:center; padding:0 5px; color:rgba(255,255,255,0.25); font-size:16px;">▶</div>

    <div style="background:rgba(104,211,145,0.12); border:1px solid rgba(104,211,145,0.35);
                padding:14px 10px; border-radius:10px; text-align:center; flex:1; min-width:80px;">
      <div style="font-size:26px; margin-bottom:5px;">🔍</div>
      <div style="color:#68d391; font-weight:700; font-size:11px; margin-bottom:2px;">STEP 2</div>
      <div style="color:#fff; font-size:12px; font-weight:600;">Parse → JSON</div>
      <div style="color:rgba(255,255,255,0.45); font-size:10px; margin-top:3px;">LLM Vision</div>
    </div>

    <div style="display:flex; align-items:center; padding:0 5px; color:rgba(255,255,255,0.25); font-size:16px;">▶</div>

    <div style="background:rgba(251,211,141,0.12); border:1px solid rgba(251,211,141,0.35);
                padding:14px 10px; border-radius:10px; text-align:center; flex:1; min-width:80px;">
      <div style="font-size:26px; margin-bottom:5px;">📑</div>
      <div style="color:#fbd38d; font-weight:700; font-size:11px; margin-bottom:2px;">STEP 3</div>
      <div style="color:#fff; font-size:12px; font-weight:600;">AdaM Specs</div>
      <div style="color:rgba(255,255,255,0.45); font-size:10px; margin-top:3px;">Excel · PDF · DOCX</div>
    </div>

    <div style="display:flex; align-items:center; padding:0 5px; color:rgba(255,255,255,0.25); font-size:16px;">▶</div>

    <div style="background:rgba(183,148,246,0.12); border:1px solid rgba(183,148,246,0.35);
                padding:14px 10px; border-radius:10px; text-align:center; flex:1; min-width:80px;">
      <div style="font-size:26px; margin-bottom:5px;">🛠️</div>
      <div style="color:#b794f4; font-weight:700; font-size:11px; margin-bottom:2px;">STEP 4</div>
      <div style="color:#fff; font-size:12px; font-weight:600;">Skills Editor</div>
      <div style="color:rgba(255,255,255,0.45); font-size:10px; margin-top:3px;">R Patterns</div>
    </div>

    <div style="display:flex; align-items:center; padding:0 5px; color:rgba(255,255,255,0.25); font-size:16px;">▶</div>

    <div style="background:rgba(252,129,74,0.12); border:1px solid rgba(252,129,74,0.35);
                padding:14px 10px; border-radius:10px; text-align:center; flex:1; min-width:80px;">
      <div style="font-size:26px; margin-bottom:5px;">💻</div>
      <div style="color:#fc814a; font-weight:700; font-size:11px; margin-bottom:2px;">STEP 5</div>
      <div style="color:#fff; font-size:12px; font-weight:600;">Generate &amp; QC</div>
      <div style="color:rgba(255,255,255,0.45); font-size:10px; margin-top:3px;">LLM Compiler</div>
    </div>

    <div style="display:flex; align-items:center; padding:0 5px; color:rgba(255,255,255,0.25); font-size:16px;">▶</div>

    <div style="background:rgba(99,179,237,0.12); border:1px solid rgba(99,179,237,0.35);
                padding:14px 10px; border-radius:10px; text-align:center; flex:1; min-width:80px;">
      <div style="font-size:26px; margin-bottom:5px;">▶️</div>
      <div style="color:#63b3ed; font-weight:700; font-size:11px; margin-bottom:2px;">STEP 6</div>
      <div style="color:#fff; font-size:12px; font-weight:600;">Run &amp; Export</div>
      <div style="color:rgba(255,255,255,0.45); font-size:10px; margin-top:3px;">CSV · PKL</div>
    </div>

  </div>
  <div style="text-align:center; margin-top:14px;">
    <span style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1);
                 padding:4px 14px; border-radius:20px; color:rgba(255,255,255,0.4); font-size:11px;">
      🔒 Your dataset never leaves your machine — only table structure &amp; specs go to the LLM
    </span>
  </div>
</div>
""")

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in {
    "table_json":       None,
    "adam_specs":       None,
    "r_code":           "",
    "qc_result":        None,
    "result_csv_path":  None,
    "run_log":          "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def load_skills() -> str:
    return SKILLS_PATH.read_text(encoding="utf-8") if SKILLS_PATH.exists() else ""


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
    st.markdown("## Step 1 · Upload & Parse Mock Shell")

    col_info, col_dl = st.columns([3, 1])
    with col_info:
        st.markdown(
            "Upload a **PNG, JPG, PDF, or DOCX** mock shell. "
            "The LLM extracts columns, rows, statistics, and metadata into a structured JSON."
        )
    with col_dl:
        sample = _sample_bytes("sample_shell_annotated.png")
        if sample:
            st.download_button(
                label="⬇️ Sample shell",
                data=sample,
                file_name="sample_shell_annotated.png",
                mime="image/png",
                use_container_width=True,
                help="Annotated oncology efficacy mock shell",
            )

    uploaded_file = st.file_uploader(
        "Choose a mock shell file",
        type=["png", "jpg", "jpeg", "pdf", "docx"],
        help="Supported: PNG/JPG (vision), PDF, Word DOCX",
    )

    if uploaded_file:
        ext = uploaded_file.name.rsplit(".", 1)[-1].lower()

        col_a, col_b = st.columns([2, 3])
        with col_a:
            st.info(f"**{uploaded_file.name}** · {uploaded_file.size:,} bytes · `.{ext}`")
        with col_b:
            if ext in ("png", "jpg", "jpeg"):
                st.caption("Image preview ↓")

        if ext in ("png", "jpg", "jpeg"):
            st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)
            uploaded_file.seek(0)

        parse_btn = st.button("🔍 Parse Shell → JSON", type="primary", use_container_width=False)

        if parse_btn:
            if not API_KEY:
                st.error("Enter your API key in the sidebar first.")
                st.stop()
            file_bytes = uploaded_file.read()
            with st.spinner(f"Sending to **{model}** for parsing…"):
                try:
                    kwargs = dict(api_key=API_KEY, provider=provider, model=model)
                    if ext in ("png", "jpg", "jpeg"):
                        result = parse_png(file_bytes, **kwargs)
                    elif ext == "docx":
                        result = parse_docx(file_bytes, **kwargs)
                    elif ext == "pdf":
                        result = parse_pdf(file_bytes, **kwargs)
                    else:
                        st.error(f"Unsupported file type: .{ext}")
                        result = None

                    if result:
                        st.session_state.table_json = result
                        st.success("Parsing complete! Proceed to Step 2.")
                except Exception as e:
                    st.error(f"Parsing failed: {e}")

    if st.session_state.table_json:
        st.markdown("---")
        st.markdown("### Extracted JSON")
        st.caption("Review and edit before generating code.")

        json_str = st.text_area(
            "Table JSON",
            value=json.dumps(st.session_state.table_json, indent=2),
            height=360,
            label_visibility="collapsed",
        )
        c1, c2 = st.columns([1, 6])
        with c1:
            if st.button("💾 Save edits", key="save_json"):
                try:
                    st.session_state.table_json = json.loads(json_str)
                    st.success("JSON updated.")
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")

        with st.expander("🔎 Parsed structure preview"):
            tj   = st.session_state.table_json
            meta = tj.get("table_metadata", {})
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Title", meta.get("title", "N/A")[:40] + "…" if len(meta.get("title","")) > 40 else meta.get("title","N/A"))
            mc2.metric("Population", meta.get("population", "N/A") or "N/A")
            mc3.metric("Dataset", meta.get("dataset_source", "N/A") or "N/A")

            cols = tj.get("columns", [])
            rows = tj.get("rows", [])
            if cols:
                st.markdown("**Columns**")
                st.dataframe(pd.DataFrame(cols), use_container_width=True, hide_index=True)
            if rows:
                st.markdown("**Rows**")
                st.dataframe(
                    pd.DataFrame([{
                        "label":        r.get("label"),
                        "analysis_var": r.get("analysis_var"),
                        "stats":        ", ".join(r.get("stats", [])),
                    } for r in rows]),
                    use_container_width=True, hide_index=True,
                )
    else:
        st.info("Upload a file and click **Parse Shell → JSON** to begin.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — AdaM Specs
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## Step 2 · Upload AdaM Specifications")

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
                label="⬇️ Sample AdaM specs",
                data=sample_specs,
                file_name="sample_adam_specs.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                help="Sample ADRS AdaM spec with variables, codelists, conditions",
            )

    adam_file = st.file_uploader(
        "Choose an AdaM spec file",
        type=["xlsx", "xls", "pdf", "docx"],
        help="Supported: Excel (.xlsx/.xls), PDF, Word DOCX",
    )

    if adam_file:
        adam_ext = adam_file.name.rsplit(".", 1)[-1].lower()
        st.info(f"**{adam_file.name}** · {adam_file.size:,} bytes · `.{adam_ext}`")

        if st.button("🔍 Parse AdaM Specs → JSON", type="primary"):
            if not API_KEY:
                st.error("Enter your API key in the sidebar first.")
                st.stop()
            file_bytes = adam_file.read()
            with st.spinner(f"Sending to **{model}** for AdaM spec parsing…"):
                try:
                    kwargs = dict(api_key=API_KEY, provider=provider, model=model)
                    if adam_ext in ("xlsx", "xls"):
                        result = parse_adam_excel(file_bytes, **kwargs)
                    elif adam_ext == "pdf":
                        result = parse_adam_pdf(file_bytes, **kwargs)
                    elif adam_ext == "docx":
                        result = parse_adam_docx(file_bytes, **kwargs)
                    else:
                        st.error(f"Unsupported file type: .{adam_ext}")
                        result = None

                    if result:
                        st.session_state.adam_specs = result
                        st.success("AdaM specs parsed! Proceed to Step 4.")
                except Exception as e:
                    st.error(f"AdaM parsing failed: {e}")

    if st.session_state.adam_specs:
        st.markdown("---")
        st.markdown("### Extracted AdaM Specs JSON")
        st.caption("Review and edit — these feed directly into the R code generator.")

        adam_str = st.text_area(
            "AdaM Specs JSON",
            value=json.dumps(st.session_state.adam_specs, indent=2),
            height=400,
            label_visibility="collapsed",
        )
        c1, _ = st.columns([1, 6])
        with c1:
            if st.button("💾 Save AdaM edits"):
                try:
                    st.session_state.adam_specs = json.loads(adam_str)
                    st.success("AdaM specs updated.")
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")

        with st.expander("🔎 AdaM specs summary"):
            specs = st.session_state.adam_specs
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Dataset", specs.get("dataset", "N/A"))
            sc2.metric("Treatment Var", specs.get("treatment_variable", "N/A"))
            sc3.metric("Pop Flags", len(specs.get("population_flags", [])))

            kv = specs.get("key_variables", [])
            if kv:
                st.markdown("**Key Variables**")
                st.dataframe(pd.DataFrame(kv), use_container_width=True, hide_index=True)
            ac = specs.get("analysis_conditions", [])
            if ac:
                st.markdown("**Analysis Conditions**")
                st.dataframe(pd.DataFrame(ac), use_container_width=True, hide_index=True)
    else:
        st.info("Upload an AdaM spec file and click **Parse AdaM Specs → JSON**.")
        st.caption("⚠️ Skipping is allowed — the LLM will use only the shell JSON and skills guide.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Skills Editor
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## Step 3 · Skills Editor")
    st.markdown(
        "This is the **system prompt** for the code generator — it defines which R packages "
        "and patterns to use for each table type. Edit to add new skills or adjust existing ones."
    )

    skills_content = st.text_area(
        "skills.md content",
        value=load_skills(),
        height=580,
        label_visibility="collapsed",
    )
    c1, _ = st.columns([1, 6])
    with c1:
        if st.button("💾 Save skills.md", type="primary"):
            SKILLS_PATH.write_text(skills_content, encoding="utf-8")
            st.success("skills.md saved.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — Generate & QC
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("## Step 4 · Generate R Code & QC Review")

    if not st.session_state.table_json:
        st.warning("Complete Step 1 first — parse a mock shell to get the table JSON.")
    else:
        meta = st.session_state.table_json.get("table_metadata", {})
        specs_label = "✅ AdaM specs loaded" if st.session_state.adam_specs else "⚠️ No AdaM specs"

        st.info(
            f"**Table:** {meta.get('title', 'Unknown')}  |  "
            f"**Dataset:** {meta.get('dataset_source', 'Unknown')}  |  {specs_label}  |  "
            f"**Model:** {provider} · {model}"
        )

        c1, _ = st.columns([1, 5])
        with c1:
            gen_btn = st.button("⚡ Generate R Script", type="primary", use_container_width=True)

        if gen_btn:
            if not API_KEY:
                st.error("Enter your API key in the sidebar first.")
                st.stop()
            with st.spinner(f"Calling **{model}** to generate R code…"):
                try:
                    code = generate_r_script(
                        table_json=st.session_state.table_json,
                        skills_md=load_skills(),
                        adam_specs=st.session_state.adam_specs,
                        api_key=API_KEY,
                        provider=provider,
                        model=model,
                    )
                    st.session_state.r_code    = code
                    st.session_state.qc_result = None
                    st.success("R script generated! Run QC below or proceed to Step 5.")
                except Exception as e:
                    st.error(f"Code generation failed: {e}")

        if st.session_state.r_code:
            st.markdown("---")
            st.markdown("### Generated R Script")

            edited_code = st.text_area(
                "R script",
                value=st.session_state.r_code,
                height=420,
                label_visibility="collapsed",
                key="r_code_editor",
            )

            c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
            with c1:
                if st.button("💾 Save edits", use_container_width=True, key="save_r"):
                    st.session_state.r_code    = edited_code
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
                if not API_KEY:
                    st.error("Enter your API key in the sidebar first.")
                    st.stop()
                with st.spinner("QC agent reviewing generated code…"):
                    try:
                        qc = qc_r_script(
                            r_code=edited_code,
                            table_json=st.session_state.table_json,
                            adam_specs=st.session_state.adam_specs,
                            api_key=API_KEY,
                            provider=provider,
                            model=model,
                        )
                        st.session_state.qc_result = qc
                    except Exception as e:
                        st.error(f"QC agent failed: {e}")

            # ── QC results ────────────────────────────────────────────────────
            if st.session_state.qc_result:
                qc       = st.session_state.qc_result
                passed   = qc.get("qc_passed", False)
                issues   = qc.get("issues", [])
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
                                st.success("Corrected code applied. Proceed to Step 5.")
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
    st.markdown("## Step 5 · Run R Script & Download Results")

    # ── Sample dataset download ───────────────────────────────────────────────
    sample_adrs = _sample_bytes("sample_adrs.csv")
    if sample_adrs:
        st.info(
            "**New to the tool?** Use the sample ADRS dataset below — it matches the sample "
            "AdaM specs (Tab 2) and sample mock shell (Tab 1) exactly.",
            icon="💡",
        )
        st.download_button(
            label="⬇️ Download sample_adrs.csv (90 subjects · 3 arms · BOR)",
            data=sample_adrs,
            file_name="sample_adrs.csv",
            mime="text/csv",
            use_container_width=False,
        )
        st.divider()

    if not st.session_state.r_code:
        st.warning("Complete Step 4 first — generate an R script.")
    else:
        qc = st.session_state.qc_result
        if qc and not qc.get("qc_passed", True):
            st.warning("⚠️ QC found issues. Consider applying QC corrections in Step 4 first.")

        # ── Rscript detection ─────────────────────────────────────────────────
        from r_executor import _find_rscript
        _detected = _find_rscript()

        with st.expander("⚙️ Rscript path", expanded=(_detected is None)):
            if _detected:
                st.success(f"Rscript detected: `{_detected}`", icon="✅")
            else:
                st.error(
                    "Rscript.exe not found automatically. "
                    "Enter the full path below.",
                    icon="❌",
                )
            rscript_override = st.text_input(
                "Override Rscript path (leave blank to use detected path)",
                value="" if _detected else r"C:\Program Files\R\R-4.5.3\bin\Rscript.exe",
                placeholder=r"C:\Program Files\R\R-4.x.x\bin\Rscript.exe",
            )
        RSCRIPT_PATH = rscript_override.strip() or _detected

        st.markdown(
            "Upload your dataset file (or enter its path) and click **Run**. "
            "The app injects `data_path` and executes the script locally via Rscript."
        )

        col_up, col_path = st.columns(2)
        with col_up:
            data_file = st.file_uploader(
                "Upload dataset file",
                type=["sas7bdat", "csv", "rdata", "rda"],
                help="SAS7BDAT, CSV, RData/Rda",
            )
        with col_path:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            direct_path = st.text_input(
                "— or enter full path to dataset on this machine —",
                placeholder=r"C:\data\adrs.sas7bdat",
            )

        run_btn = st.button("▶️ Run R Script", type="primary")

        if run_btn:
            if not RSCRIPT_PATH:
                st.error(
                    "Rscript path is not set. Expand **⚙️ Rscript path** above and enter the path manually."
                )
                st.stop()

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
                    success, csv_path, log = run_r_script(
                        st.session_state.r_code, resolved_path, rscript_path=RSCRIPT_PATH
                    )
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
            st.markdown("---")
            st.markdown("### Result: `final_df`")
            df = pd.read_csv(st.session_state.result_csv_path)
            st.markdown(f"**{len(df):,} rows × {len(df.columns)} columns**")
            st.dataframe(df, use_container_width=True)

            import pickle
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    label="⬇️ Download final_df.csv",
                    data=df.to_csv(index=False),
                    file_name="final_df.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with c2:
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
    st.markdown("## How to Use TLF Output Generator")

    st.markdown("""
### Workflow (one table at a time)

| Step | Tab | What you do | What happens |
|------|-----|-------------|--------------|
| 1 | Parse Shell | Upload PNG / PDF / DOCX mock shell | LLM extracts table structure → JSON |
| 2 | AdaM Specs | Upload Excel / PDF / DOCX AdaM specs | LLM extracts variables, codelists, conditions → JSON |
| 3 | Skills Editor | Review / edit skills.md | Defines R packages & coding patterns |
| 4 | Generate & QC | Click Generate, then Run QC | LLM writes R code; QC agent reviews and corrects |
| 5 | Run & Download | Upload dataset, click Run | Rscript executes locally → download final_df |
""")

    st.markdown("---")
    st.markdown("""
### Supported AI Providers

| Provider | Models | Notes |
|----------|--------|-------|
| **OpenAI** | gpt-4o, gpt-4o-mini | Both `sk-` and `sk-proj-` keys work |
| **Google Gemini** | gemini-2.0-flash, gemini-1.5-pro/flash | Get key at aistudio.google.com |
| **Anthropic Claude** | claude-sonnet-4-6, opus-4-6, haiku-4-5 | Get key at console.anthropic.com |

**API Key Troubleshooting:**
- Error `invalid_api_key`: Re-copy the key carefully — trailing spaces, periods, or line breaks break it.
- `sk-proj-` keys (OpenAI Project keys) are fully valid — you do **not** need a separate key per project.
- Install extra packages if needed: `pip install google-generativeai anthropic`
""")

    st.markdown("---")
    st.markdown("""
### Supported Input Formats

| File | Parser |
|------|--------|
| PNG / JPG | LLM Vision API (image sent directly) |
| PDF | pdfplumber → text → LLM |
| DOCX | python-docx → text → LLM |
| Excel (.xlsx) | openpyxl → text → LLM |

### QC Agent
Checks generated R code for:
- Wrong/invented variable names vs. AdaM specs
- Missing population filters (`FASFL='Y'`, `ANL01FL='Y'`)
- Missing or wrong `PARAMCD` filter
- Wrong treatment variable (`TRTP` vs `TRTA`)
- Incorrect Tplyr functions
- R syntax issues

### Notes
- R packages (Tplyr, dplyr, haven, etc.) are auto-installed on first run.
- Rscript must be installed (auto-detected from `C:/Program Files/R/`).
- Your dataset is never sent to the LLM — only the shell structure and specs.
""")
