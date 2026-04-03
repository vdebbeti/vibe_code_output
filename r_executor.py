"""
R Executor: injects data_path into the R script and runs it
via subprocess Rscript. Captures final_df as a CSV.
"""
import os
import subprocess
import tempfile
import platform
from pathlib import Path


def _find_rscript() -> str:
    """Find the Rscript executable on Windows or Unix."""
    if platform.system() == "Windows":
        r_base = Path(r"C:\Program Files\R")
        if r_base.exists():
            # Pick the highest installed R version
            versions = sorted(
                [d for d in r_base.iterdir() if d.is_dir()],
                reverse=True,
            )
            for version_dir in versions:
                rscript = version_dir / "bin" / "Rscript.exe"
                if rscript.exists():
                    return str(rscript)
    return "Rscript"  # fallback: rely on PATH


def run_r_script(r_code: str, data_path: str) -> tuple:
    """
    Inject data_path into the R script, run it, capture final_df as CSV.

    Args:
        r_code:     The R script string (must produce `final_df`)
        data_path:  Absolute path to the dataset file

    Returns:
        (success: bool, output_csv_path: str, log: str)
    """
    rscript_exe = _find_rscript()

    # Temp directory for this run
    tmp_dir = tempfile.mkdtemp(prefix="r_exec_")
    output_csv = os.path.join(tmp_dir, "final_df.csv")
    script_path = os.path.join(tmp_dir, "generated_script.R")

    # R wants forward slashes
    safe_data_path = data_path.replace("\\", "/")
    safe_output_csv = output_csv.replace("\\", "/")

    full_script = (
        '# === INJECTED BY APP ===\n'
        f'data_path <- "{safe_data_path}"\n'
        f'output_path <- "{safe_output_csv}"\n'
        '# =======================\n\n'
        + r_code
        + '\n\n'
        '# === SAVE OUTPUT ===\n'
        'if (exists("final_df") && is.data.frame(final_df)) {\n'
        '  write.csv(final_df, output_path, row.names = FALSE)\n'
        '  cat("SUCCESS: final_df saved\\n")\n'
        '} else {\n'
        '  stop("ERROR: final_df was not created or is not a data frame.")\n'
        '}\n'
    )

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(full_script)

    try:
        result = subprocess.run(
            [rscript_exe, "--vanilla", script_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        log = result.stdout + "\n" + result.stderr

        if result.returncode == 0 and os.path.exists(output_csv):
            return True, output_csv, log
        else:
            return False, "", log

    except FileNotFoundError:
        return False, "", (
            f"Rscript not found at '{rscript_exe}'.\n"
            "Please ensure R is installed and Rscript.exe is on your PATH."
        )
    except subprocess.TimeoutExpired:
        return False, "", "R script timed out after 5 minutes."
    except Exception as e:
        return False, "", f"Unexpected error: {str(e)}"
