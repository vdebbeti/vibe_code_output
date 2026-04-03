"""
R Executor: injects data_path into the R script and runs it
via subprocess Rscript. Captures final_df as a CSV.
"""
import os
import subprocess
import tempfile
from pathlib import Path


def _find_rscript() -> str | None:
    """
    Find Rscript.exe using multiple strategies (Windows-focused).
    Returns the path string, or None if not found anywhere.
    """
    candidates: list[Path] = []

    # 1. Windows registry (most reliable — set at install time)
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\R-core\R", r"SOFTWARE\WOW6432Node\R-core\R"):
                try:
                    with winreg.OpenKey(root, sub) as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                        candidates.append(Path(install_path) / "bin" / "Rscript.exe")
                except (FileNotFoundError, OSError):
                    pass
    except ImportError:
        pass  # not on Windows

    # 2. Well-known Windows install directories
    for base in [
        Path(r"C:\Program Files\R"),
        Path(r"C:\Program Files (x86)\R"),
        Path(os.path.expanduser(r"~\AppData\Local\Programs\R")),
    ]:
        if base.exists():
            for version_dir in sorted(base.iterdir(), reverse=True):
                if version_dir.is_dir():
                    candidates.append(version_dir / "bin" / "Rscript.exe")
                    candidates.append(version_dir / "bin" / "x64" / "Rscript.exe")

    # 3. Check all candidates in order
    for path in candidates:
        if path.exists():
            return str(path)

    # 4. Last resort — rely on PATH
    try:
        result = subprocess.run(
            ["Rscript", "--version"],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            return "Rscript"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def run_r_script(r_code: str, data_path: str, rscript_path: str | None = None) -> tuple:
    """
    Inject data_path into the R script, run it, capture final_df as CSV.

    Args:
        r_code:        The R script string (must produce `final_df`)
        data_path:     Absolute path to the dataset file
        rscript_path:  Override path to Rscript.exe (optional)

    Returns:
        (success: bool, output_csv_path: str, log: str)
    """
    rscript_exe = rscript_path or _find_rscript()

    if not rscript_exe:
        return False, "", (
            "Rscript.exe not found.\n\n"
            "Please enter the full path to Rscript.exe in the box above.\n"
            "Default Windows location: C:\\Program Files\\R\\R-x.x.x\\bin\\Rscript.exe"
        )

    tmp_dir = tempfile.mkdtemp(prefix="r_exec_")
    output_csv  = os.path.join(tmp_dir, "final_df.csv")
    script_path = os.path.join(tmp_dir, "generated_script.R")

    # R wants forward slashes
    safe_data_path   = data_path.replace("\\", "/")
    safe_output_csv  = output_csv.replace("\\", "/")

    full_script = (
        '# === INJECTED BY APP ===\n'
        f'data_path   <- "{safe_data_path}"\n'
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

    # Use shell=True with a quoted command string so Windows cmd.exe handles
    # path resolution — this avoids Git Bash / MSYS2 subprocess path issues.
    cmd = f'"{rscript_exe}" --vanilla "{script_path}"'

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            shell=True,          # lets cmd.exe resolve the Windows path
        )
        log = result.stdout + "\n" + result.stderr

        if result.returncode == 0 and os.path.exists(output_csv):
            return True, output_csv, log
        else:
            return False, "", log

    except subprocess.TimeoutExpired:
        return False, "", "R script timed out after 5 minutes."
    except Exception as e:
        return False, "", f"Unexpected error: {e}"
