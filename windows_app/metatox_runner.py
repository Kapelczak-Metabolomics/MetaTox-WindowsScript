"""Run the MetaTox Linux pipeline from Windows via WSL2."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional


LogCallback = Callable[[str], None]


@dataclass
class MetaToxOptions:
    input_file: str
    outdir: str = "Results_Prediction"
    biotrans_type: str = "allHuman"
    nstep: int = 1
    cmode: int = 3
    phase1: int = 1
    phase2: int = 1
    phase_gloryx: str = "phase_1_and_2"
    predictor_activate: bool = False
    keep_tmp: bool = False
    metatox_root: Optional[str] = None


@dataclass
class EnvironmentStatus:
    wsl_available: bool = False
    wsl_distro: Optional[str] = None
    singularity_available: bool = False
    metatox_root: Optional[str] = None
    metatox_script_found: bool = False
    issues: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def get_application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_metatox_root(explicit_root: Optional[str] = None) -> Path:
    candidates: List[Path] = []
    if explicit_root:
        candidates.append(Path(explicit_root))
    app_dir = get_application_dir()
    candidates.append(app_dir)
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            candidates.append(Path(bundle_dir))
    candidates.extend([app_dir.parent, Path.cwd()])
    for candidate in candidates:
        script = candidate / "Metatox.sh"
        if script.is_file():
            return candidate.resolve()
    return app_dir.resolve()


def windows_to_wsl_path(path: str | Path) -> str:
    text = str(path)
    normalized = text.replace("\\", "/")
    drive_match = re.match(r"^([A-Za-z]):/(.*)$", normalized)
    if drive_match:
        letter = drive_match.group(1).lower()
        tail = drive_match.group(2).lstrip("/")
        return f"/mnt/{letter}/{tail}" if tail else f"/mnt/{letter}"

    resolved = Path(path).resolve()
    drive = resolved.drive
    if drive:
        letter = drive[0].lower()
        tail = str(resolved)[len(drive) :].replace("\\", "/")
        return f"/mnt/{letter}{tail}"
    return str(resolved).replace("\\", "/")


def _run_command(command: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _default_wsl_distro() -> Optional[str]:
    if not shutil.which("wsl"):
        return None
    result = _run_command(["wsl", "--status"], timeout=20)
    if result.returncode != 0 and not result.stdout and not result.stderr:
        return None
    list_result = _run_command(["wsl", "-l", "-q"], timeout=20)
    if list_result.returncode != 0:
        return None
    for line in list_result.stdout.splitlines():
        distro = line.strip().replace("\x00", "")
        if distro:
            return distro
    return None


def check_environment(metatox_root: Optional[str] = None) -> EnvironmentStatus:
    status = EnvironmentStatus()
    root = resolve_metatox_root(metatox_root)
    status.metatox_root = str(root)
    status.metatox_script_found = (root / "Metatox.sh").is_file()

    if not status.metatox_script_found:
        status.issues.append(
            "Metatox.sh was not found. Place MetaToxGUI.exe in the MetaTox folder "
            "or choose the MetaTox installation directory."
        )

    if not shutil.which("wsl"):
        status.issues.append(
            "WSL is not installed. Install WSL2 and a Linux distribution, then set up "
            "Singularity inside WSL as described in windows_app/README_WINDOWS.md."
        )
        return status

    status.wsl_available = True
    status.wsl_distro = _default_wsl_distro()
    if not status.wsl_distro:
        status.issues.append("No WSL Linux distribution was detected.")
        return status

    singularity_check = _run_command(
        ["wsl", "-d", status.wsl_distro, "-e", "bash", "-lc", "command -v singularity"],
        timeout=30,
    )
    status.singularity_available = singularity_check.returncode == 0 and bool(
        singularity_check.stdout.strip()
    )
    if not status.singularity_available:
        status.issues.append(
            "Singularity was not found inside WSL. Install Singularity in your WSL "
            "distribution before running predictions."
        )

    if status.wsl_available and status.metatox_script_found:
        status.notes.append(
            "MetaTox runs inside WSL2 because BioTransformer, SygMa, GLORYx, and MetaTrans "
            "require Linux containers."
        )

    return status


def _validate_input_file(input_file: str) -> None:
    path = Path(input_file)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    invalid_lines: List[str] = []
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for index, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(",", 1)
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                invalid_lines.append(f"Line {index}: {line}")
    if invalid_lines:
        sample = "\n".join(invalid_lines[:5])
        raise ValueError(
            "Input file must contain one molecule per line in the format "
            "'MoleculeName,SMILES'.\n"
            f"Invalid lines:\n{sample}"
        )


def build_shell_command(options: MetaToxOptions) -> str:
    root = resolve_metatox_root(options.metatox_root)
    wsl_root = windows_to_wsl_path(root)
    wsl_input = windows_to_wsl_path(options.input_file)
    wsl_outdir = options.outdir.replace("\\", "/").replace("'", "'\\''")

    parts = [
        f"cd '{wsl_root}'",
        "chmod +x Metatox.sh",
        "dos2unix -q Metatox.sh 2>/dev/null || true",
        "./Metatox.sh",
        f"--input '{wsl_input}'",
        f"--outdir '{wsl_outdir}'",
        f"--biotrans '{options.biotrans_type}'",
        f"--nstep '{options.nstep}'",
        f"--cmode '{options.cmode}'",
        f"--phase1 '{options.phase1}'",
        f"--phase2 '{options.phase2}'",
        f"--metabo '{options.phase_gloryx}'",
    ]
    if options.predictor_activate:
        parts.append("--predictor")
    if options.keep_tmp:
        parts.append("--tmp")

    return " && ".join(parts)


def resolve_output_directory(options: MetaToxOptions) -> Path:
    outdir = Path(options.outdir)
    if outdir.is_absolute():
        return outdir.resolve()
    return (resolve_metatox_root(options.metatox_root) / outdir).resolve()


def run_pipeline(
    options: MetaToxOptions,
    log_callback: Optional[LogCallback] = None,
    cancel_event=None,
) -> Path:
    def emit(message: str) -> None:
        if log_callback:
            log_callback(message)

    _validate_input_file(options.input_file)
    env = check_environment(options.metatox_root)
    if env.issues:
        raise RuntimeError("\n".join(env.issues))

    shell_command = build_shell_command(options)
    distro = env.wsl_distro or _default_wsl_distro()
    if not distro:
        raise RuntimeError("No WSL distribution is available.")

    emit("Starting MetaTox inside WSL2...")
    emit(f"WSL distribution: {distro}")
    emit(f"MetaTox root: {env.metatox_root}")
    emit(f"Input file: {options.input_file}")
    emit(f"Output directory: {resolve_output_directory(options)}")
    emit("")
    emit("Command:")
    emit(shell_command)
    emit("")

    process = subprocess.Popen(
        ["wsl", "-d", distro, "-e", "bash", "-lc", shell_command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    assert process.stdout is not None
    for line in process.stdout:
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            raise RuntimeError("Prediction cancelled by user.")
        emit(line.rstrip("\n"))

    return_code = process.wait()
    output_dir = resolve_output_directory(options)
    if return_code != 0:
        raise RuntimeError(
            f"MetaTox exited with code {return_code}. Check the log output above "
            f"and files in {output_dir.parent / 'log'}."
        )

    if not output_dir.exists():
        raise RuntimeError(
            f"MetaTox finished but the output directory was not created: {output_dir}"
        )

    emit("")
    emit(f"Results saved to: {output_dir}")
    return output_dir


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    opener = shutil.which("xdg-open") or shutil.which("open")
    if opener:
        subprocess.run([opener, str(path)], check=False)
    else:
        raise OSError(f"Cannot open path automatically: {path}")


def summarize_outputs(output_dir: Path) -> str:
    if not output_dir.exists():
        return "No output directory found."

    tsv_files = sorted(output_dir.glob("*_CompileResults.tsv"))
    figure_dirs = sorted(
        [item for item in output_dir.iterdir() if item.is_dir() and item.name.endswith("_figures")]
    )
    lines = [
        f"Output folder: {output_dir}",
        f"Compiled result files: {len(tsv_files)}",
        f"Figure folders: {len(figure_dirs)}",
    ]
    if tsv_files:
        lines.append("Generated files:")
        lines.extend(f"  - {path.name}" for path in tsv_files[:10])
        if len(tsv_files) > 10:
            lines.append(f"  ... and {len(tsv_files) - 10} more")
    return "\n".join(lines)
