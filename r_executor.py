"""
R Executor: injects data_path into the R script and runs it via Rscript.
Captures final_df as a CSV.

Works on:
- Streamlit Cloud (Linux) → after you add packages.txt
- Local Windows → if R is installed and Rscript is in PATH
"""

import os
import subprocess
import tempfile
import shutil
import platform
from pathlib import Path


# ── Rscript finder (now cross-platform) ─────────────────────────────────────
def _find_rscript() -> str | None:
    """
    Return the path to Rscript (or 'Rscript' if it's in PATH).
    Works on Linux (Streamlit Cloud) and Windows.
    """
    # 1. Check PATH first (this is what Streamlit Cloud uses after r-base is installed)
    rscript = shutil.which("Rscript")   # finds Rscript or Rscript.exe automatically
    if rscript:
        return rscript

    # 2. Windows fallback (only if not in PATH)
    if platform.system() == "Windows":
        # Keep your original registry + common paths logic if you want
        # (but most users have Rscript in PATH after install, so this is rarely hit)
        candidates = []
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for sub in (r"SOFTWARE\R-core\R", r"SOFTWARE\WOW6432Node\R-core\R"):
                    try:
                        with winreg.OpenKey(root, sub) as key:
                            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                            candidates.append(os.path.join(install_path, "bin", "Rscript.exe"))
                    except (FileNotFoundError, OSError):
                        pass
        except ImportError:
            pass

        for base in [r"C:\Program Files\R", r"C:\Program Files (x86)\R",
                     os.path.expanduser(r"~\AppData\Local\Programs\R")]:
            if os.path.isdir(base):
                try:
                    for ver in sorted(os.listdir(base), reverse=True):
                        for sub in ("bin\\Rscript.exe", "bin\\x64\\Rscript.exe"):
                            p = os.path.join(base, ver, sub)
                            candidates.append(p)
                except OSError:
                    pass

        for p in candidates:
            if os.path.isfile(p):
                return p

    return None


# ── Simple subprocess runner (no more Windows-only COMSPEC hacks) ─────────────
def _run_rscript(rscript_exe: str, script_path: str, timeout: int = 300):
    """
    Run Rscript with a clean list-of-args call.
    Works on both Linux and Windows. No shell=True, no COMSPEC needed.
    """
    return subprocess.run(
        [rscript_exe, "--vanilla", script_path],
        capture_output=True,
        text=True,
        timeout=timeout,
        # shell=False is default when passing a list
    )


# ── Public API (almost unchanged, just much more reliable) ───────────────────
def run_r_script(
    r_code: str,
    data_path: str,
    rscript_path: str | None = None,
) -> tuple[bool, str, str]:
    """
    Inject data_path into the R script, run it, capture final_df as CSV.

    Returns:
        (success: bool, output_csv_path: str, log: str)
    """
    # Use user-provided path if given, otherwise auto-detect
    rscript_exe = rscript_path or _find_rscript()

    if not rscript_exe:
        if platform.system() == "Linux":
            error_msg = (
                "Rscript not found on Streamlit Cloud.\n\n"
                "✅ Fix: Create a file named packages.txt in the root of your GitHub repo with:\n"
                "r-base\n"
                "r-base-dev\n"
                "(and any r-cran-xxx packages your script uses)\n\n"
                "Then redeploy. Rscript will be installed and available in PATH."
            )
        else:
            error_msg = (
                "Rscript.exe not found.\n\n"
                "1. Make sure R is installed.\n"
                "2. Add R to your PATH, or\n"
                "3. Paste the full path to Rscript.exe in the ⚙️ setting.\n"
                "Typical: C:\\Program Files\\R\\R-x.x.x\\bin\\Rscript.exe"
            )
        return False, "", error_msg

    tmp_dir = tempfile.mkdtemp(prefix="r_exec_")
    output_csv = os.path.join(tmp_dir, "final_df.csv")
    script_path = os.path.join(tmp_dir, "generated_script.R")

    # R works with forward slashes on both Windows and Linux
    safe_data = data_path.replace("\\", "/")
    safe_output = output_csv.replace("\\", "/")

    full_script = (
        "# === INJECTED BY APP ===\n"
        f'data_path   <- "{safe_data}"\n'
        f'output_path <- "{safe_output}"\n'
        "# =======================\n\n"
        + r_code
        + "\n\n"
        "# === SAVE OUTPUT ===\n"
        "if (exists('final_df') && is.data.frame(final_df)) {\n"
        "  write.csv(final_df, output_path, row.names = FALSE)\n"
        "  cat('SUCCESS: final_df saved\\n')\n"
        "} else {\n"
        "  stop('ERROR: final_df was not created or is not a data frame.')\n"
        "}\n"
    )

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(full_script)

    try:
        result = _run_rscript(rscript_exe, script_path)
        log = result.stdout + "\n" + result.stderr

        if result.returncode == 0 and os.path.exists(output_csv):
            return True, output_csv, log
        else:
            return False, "", log

    except subprocess.TimeoutExpired:
        return False, "", "R script timed out after 5 minutes."
    except Exception as e:
        return False, "", f"Unexpected error: {e}"