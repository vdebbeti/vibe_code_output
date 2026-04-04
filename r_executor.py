"""
R Executor: injects data_path into the R script and runs it via Rscript.
Captures final_df as a CSV.

Execution strategy (in order):
  1. subprocess.run([COMSPEC, '/c', rscript_exe, ...], shell=False)
     - COMSPEC = C:/WINDOWS/system32/cmd.exe (no spaces -> CreateProcess finds it)
     - cmd.exe then handles Rscript path that may have spaces
     - Works regardless of whether the parent Python uses /bin/sh or cmd.exe
  2. subprocess.run([rscript_exe, ...], shell=False) -- direct Windows CreateProcess
  3. subprocess.run(cmd_str, shell=True) -- last resort
"""
import os
import subprocess
import tempfile
from pathlib import Path


# ── Rscript finder ────────────────────────────────────────────────────────────
def _find_rscript() -> str | None:
    """
    Return the full Windows path to Rscript.exe, or None if not found.
    Tries: registry → common install dirs → PATH.
    """
    candidates: list[str] = []

    # 1. Windows registry (most authoritative)
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (
                r"SOFTWARE\R-core\R",
                r"SOFTWARE\WOW6432Node\R-core\R",
            ):
                try:
                    with winreg.OpenKey(root, sub) as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                        candidates.append(
                            os.path.join(install_path, "bin", "Rscript.exe")
                        )
                except (FileNotFoundError, OSError):
                    pass
    except ImportError:
        pass

    # 2. Enumerate C:\Program Files\R\ (and x86 variant)
    for base_str in [
        r"C:\Program Files\R",
        r"C:\Program Files (x86)\R",
        os.path.expanduser(r"~\AppData\Local\Programs\R"),
    ]:
        if os.path.isdir(base_str):
            try:
                for ver in sorted(os.listdir(base_str), reverse=True):
                    for sub in ("bin\\Rscript.exe", "bin\\x64\\Rscript.exe"):
                        candidates.append(os.path.join(base_str, ver, sub))
            except OSError:
                pass

    # Return first path that actually exists on disk
    for p in candidates:
        if os.path.isfile(p):
            return p

    # 3. Try 'Rscript' on PATH
    try:
        r = subprocess.run(
            ["Rscript", "--version"],
            capture_output=True, timeout=5,
        )
        if r.returncode == 0:
            return "Rscript"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


# ── Subprocess runner (the key fix) ──────────────────────────────────────────
def _run_rscript(rscript_exe: str, script_path: str, timeout: int = 300):
    """
    Run Rscript.exe reliably even when the parent Python is inside Git Bash /
    MSYS2 (where shell=True uses /bin/sh instead of cmd.exe).

    Strategy: call COMSPEC (cmd.exe) explicitly with shell=False.
    - C:\\Windows\\system32\\cmd.exe has NO spaces → CreateProcess finds it.
    - cmd.exe receives the Rscript path (which may have spaces) as a quoted arg.
    - No dependency on the SHELL env var.
    """
    comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")

    # Primary: route through cmd.exe (always works on Windows even in Git Bash)
    try:
        return subprocess.run(
            [comspec, "/c", rscript_exe, "--vanilla", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (FileNotFoundError, OSError):
        pass

    # Fallback 1: direct CreateProcess (works if not in Git Bash context)
    try:
        return subprocess.run(
            [rscript_exe, "--vanilla", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (FileNotFoundError, OSError):
        pass

    # Fallback 2: shell=True as last resort
    cmd_str = f'"{rscript_exe}" --vanilla "{script_path}"'
    return subprocess.run(
        cmd_str,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=True,
    )


# ── Public API ────────────────────────────────────────────────────────────────
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
    rscript_exe = rscript_path or _find_rscript()

    if not rscript_exe:
        return False, "", (
            "Rscript.exe not found.\n\n"
            "Expand ⚙️ Rscript path above and paste the full path.\n"
            r"Typical location: C:\Program Files\R\R-x.x.x\bin\Rscript.exe"
        )

    tmp_dir = tempfile.mkdtemp(prefix="r_exec_")
    output_csv  = os.path.join(tmp_dir, "final_df.csv")
    script_path = os.path.join(tmp_dir, "generated_script.R")

    # R prefers forward slashes in paths
    safe_data   = data_path.replace("\\", "/")
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
