"""Run the MetaTox shell pipeline from the web application."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


LogCallback = Callable[[str], None]


@dataclass
class PipelineOptions:
    input_file: Path
    outdir: str = "data/output/Results_Prediction"
    biotrans_type: str = "allHuman"
    nstep: int = 1
    cmode: int = 3
    phase1: int = 1
    phase2: int = 1
    phase_gloryx: str = "phase_1_and_2"
    predictor_activate: bool = False
    keep_tmp: bool = False
    work_dir: Optional[Path] = None


@dataclass
class EnvironmentStatus:
    singularity_available: bool
    metatox_script_found: bool
    metapredictor_available: bool
    work_dir: Path
    issues: List[str]
    notes: List[str]


def get_work_dir() -> Path:
    return Path(os.environ.get("APP_ROOT", "/app")).resolve()


def metapredictor_is_available(work_dir: Optional[Path] = None) -> bool:
    root = work_dir or get_work_dir()
    predictor_script = root / "Meta-Predictor" / "predict-top15.sh"
    return predictor_script.is_file() and bool(shutil.which("conda"))


def check_environment() -> EnvironmentStatus:
    work_dir = get_work_dir()
    issues: List[str] = []
    notes: List[str] = []

    singularity = shutil.which("singularity") or shutil.which("apptainer")
    if not singularity:
        issues.append("Singularity/Apptainer is not available inside the container.")
    else:
        notes.append(f"Container runtime: {singularity}")

    script = work_dir / "Metatox.sh"
    if not script.is_file():
        issues.append(f"Metatox.sh was not found in {work_dir}.")

    predictor_ready = metapredictor_is_available(work_dir)
    if not predictor_ready:
        notes.append(
            "Meta-Predictor is not installed in this container. "
            "Leave it disabled unless you add the Meta-Predictor repository and Conda."
        )

    if not issues:
        notes.append("The web UI will run predictions through the bundled Metatox.sh pipeline.")

    return EnvironmentStatus(
        singularity_available=bool(singularity),
        metatox_script_found=script.is_file(),
        metapredictor_available=predictor_ready,
        work_dir=work_dir,
        issues=issues,
        notes=notes,
    )


def validate_input_file(input_file: Path) -> None:
    if not input_file.is_file():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    invalid_lines: List[str] = []
    with input_file.open("r", encoding="utf-8-sig", errors="replace") as handle:
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
            "Input must contain one molecule per line as MoleculeName,SMILES.\n"
            f"Invalid lines:\n{sample}"
        )


def resolve_output_dir(options: PipelineOptions) -> Path:
    work_dir = options.work_dir or get_work_dir()
    outdir = Path(options.outdir)
    if outdir.is_absolute():
        return outdir.resolve()
    return (work_dir / outdir).resolve()


def build_command(options: PipelineOptions) -> List[str]:
    work_dir = options.work_dir or get_work_dir()
    command = [
        "bash",
        str(work_dir / "Metatox.sh"),
        "--input",
        str(options.input_file.resolve()),
        "--outdir",
        options.outdir,
        "--biotrans",
        options.biotrans_type,
        "--nstep",
        str(options.nstep),
        "--cmode",
        str(options.cmode),
        "--phase1",
        str(options.phase1),
        "--phase2",
        str(options.phase2),
        "--metabo",
        options.phase_gloryx,
    ]
    if options.predictor_activate:
        command.append("--predictor")
    if options.keep_tmp:
        command.append("--tmp")
    return command


def run_pipeline(
    options: PipelineOptions,
    log_callback: Optional[LogCallback] = None,
    cancel_event=None,
) -> Path:
    def emit(message: str) -> None:
        if log_callback:
            log_callback(message)

    validate_input_file(options.input_file)
    env_status = check_environment()
    if env_status.issues:
        raise RuntimeError("\n".join(env_status.issues))

    work_dir = options.work_dir or get_work_dir()
    command = build_command(options)
    output_dir = resolve_output_dir(options)

    emit("Starting MetaTox pipeline...")
    emit(f"Working directory: {work_dir}")
    emit(f"Input file: {options.input_file}")
    emit(f"Output directory: {output_dir}")
    emit("Command: " + " ".join(command))
    emit("")

    run_env = os.environ.copy()
    run_env.setdefault("METATOX_VERBOSE", "true")
    run_env.setdefault("METATOX_NATIVE_COMPILE", "true")
    run_env.pop("APPTAINER_BINDPATH", None)
    run_env.pop("SINGULARITY_BINDPATH", None)
    run_env.setdefault("APPTAINER_NO_MOUNT", "cwd,home,/etc/localtime")
    run_env.setdefault("SINGULARITY_NO_MOUNT", "cwd,home,/etc/localtime")
    run_env.setdefault("APPTAINER_TMPDIR", "/tmp/apptainer")
    run_env.setdefault("SINGULARITY_TMPDIR", "/tmp/apptainer")

    process = subprocess.Popen(
        command,
        cwd=work_dir,
        env=run_env,
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
            raise RuntimeError("Prediction cancelled.")
        emit(line.rstrip("\n"))

    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"MetaTox exited with code {return_code}. Check the log panel and {work_dir / 'log'}."
        )

    if not output_dir.exists():
        raise RuntimeError(f"MetaTox finished but no output directory was created: {output_dir}")

    if not list(output_dir.glob("*_CompileResults.tsv")):
        raise RuntimeError(
            f"MetaTox finished but no compiled results were found in {output_dir}. "
            f"Check {work_dir / 'log'} for step errors."
        )

    emit("")
    emit(f"Results saved to: {output_dir}")
    return output_dir


def summarize_outputs(output_dir: Path) -> str:
    if not output_dir.exists():
        return "No output directory found."

    tsv_files = sorted(output_dir.glob("*_CompileResults.tsv"))
    figure_dirs = sorted(
        path for path in output_dir.iterdir() if path.is_dir() and path.name.endswith("_figures")
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


def zip_output_directory(output_dir: Path, destination: Path | None = None) -> Path:
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    result_files = sorted(output_dir.glob("*_CompileResults.tsv"))
    if not result_files:
        raise RuntimeError(
            f"No compiled result files were found in {output_dir}. "
            "The pipeline may have failed before generating outputs."
        )

    archive_path = (destination or output_dir / "MetaTox_results.zip").resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()

    files_added = 0
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file() and path.resolve() != archive_path:
                archive.write(path, arcname=path.relative_to(output_dir).as_posix())
                files_added += 1

    if files_added == 0 or not archive_path.is_file() or archive_path.stat().st_size == 0:
        raise RuntimeError(f"Results archive was not created correctly: {archive_path}")

    return archive_path


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "metatox_input.txt"
