#!/usr/bin/env python3
"""Ensure a complete writable BioTransformer runtime (jar + btkb + supportfiles + config)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

BIOTRANSFORMER_IMAGE = os.environ.get(
    "BIOTRANSFORMER_IMAGE",
    "https://depot.galaxyproject.org/singularity/biotransformer:3.0.20230403--hdfd78af_0",
)
DEFAULT_RUNTIME = os.environ.get(
    "BIOTRANSFORMER_RUNTIME",
    "/var/lib/metatox/biotransformer-runtime",
)
OFFICIAL_ZIP_URL = os.environ.get(
    "BIOTRANSFORMER_ZIP_URL",
    "https://bitbucket.org/wishartlab/biotransformer3.0jar/get/3f0ab32d3496e05e8084ceff249d18a067ff601e.zip",
)
READY_MARKER = ".ready-complete-v1"


def find_singularity() -> str:
    for name in ("singularity", "apptainer"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("singularity/apptainer not found")


def runtime_complete(runtime: Path) -> bool:
    jar_files = list(runtime.glob("*.jar"))
    return (
        bool(jar_files)
        and (runtime / "btkb").is_dir()
        and (runtime / "supportfiles").is_dir()
        and (runtime / "config.json").is_file()
        and (runtime / "supportfiles" / "MVDModels").exists()
    )


def extract_from_image(runtime: Path) -> None:
    singularity = find_singularity()
    runtime.mkdir(parents=True, exist_ok=True)
    cmd = [
        singularity,
        "exec",
        "--no-mount",
        "cwd,home,tmp",
        "--writable-tmpfs",
        "-B",
        f"{runtime}:/bt-export",
        BIOTRANSFORMER_IMAGE,
        "bash",
        "-lc",
        """
set -euo pipefail
src=""
if command -v biotransformer >/dev/null 2>&1; then
  script="$(readlink -f "$(command -v biotransformer)")"
  src="$(dirname "${script}")"
fi
if [ -z "${src}" ] || [ ! -d "${src}" ]; then
  src="$(ls -d /usr/local/share/biotransformer-* 2>/dev/null | head -n 1 || true)"
fi
if [ -z "${src}" ] || [ ! -d "${src}" ]; then
  echo "ERROR: could not locate BioTransformer package directory inside the image" >&2
  ls -la /usr/local/share >&2 || true
  exit 1
fi
echo "Copying from ${src}"
cp -a "${src}/." /bt-export/
""",
    ]
    subprocess.run(cmd, check=True)


def download_official_package(runtime: Path) -> None:
    print(f"Downloading complete BioTransformer package from {OFFICIAL_ZIP_URL} ...")
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="biotransformer-zip-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "biotransformer.zip"
        with urllib.request.urlopen(OFFICIAL_ZIP_URL, timeout=600) as response:
            zip_path.write_bytes(response.read())
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
        roots = [path for path in extract_dir.iterdir() if path.is_dir()]
        if not roots:
            raise RuntimeError("Official BioTransformer zip did not contain a top-level directory")
        src = roots[0]
        for item in src.iterdir():
            destination = runtime / item.name
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)


def prepare_runtime(runtime: Path) -> Path:
    marker = runtime / READY_MARKER
    if marker.is_file() and runtime_complete(runtime):
        print(f"BioTransformer runtime ready: {runtime}")
        return runtime

    if runtime.exists():
        for child in runtime.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    runtime.mkdir(parents=True, exist_ok=True)

    # Prefer the official complete package; fall back to image extract then repair.
    try:
        download_official_package(runtime)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: official package download failed ({exc}); extracting from image...", file=sys.stderr)
        extract_from_image(runtime)

    if not runtime_complete(runtime):
        print("Runtime incomplete after primary prepare; merging official package...", file=sys.stderr)
        download_official_package(runtime)

    if not runtime_complete(runtime):
        missing = []
        if not list(runtime.glob("*.jar")):
            missing.append("*.jar")
        if not (runtime / "btkb").is_dir():
            missing.append("btkb/")
        if not (runtime / "supportfiles").is_dir():
            missing.append("supportfiles/")
        if not (runtime / "config.json").is_file():
            missing.append("config.json")
        raise RuntimeError(f"BioTransformer runtime incomplete; missing: {', '.join(missing)}")

    # Make DB/model files writable for lock files.
    for path in runtime.rglob("*"):
        try:
            if path.is_dir():
                path.chmod(path.stat().st_mode | 0o700)
            else:
                path.chmod(path.stat().st_mode | 0o600)
        except OSError:
            pass

    marker.write_text("ok\n", encoding="utf-8")
    print(f"BioTransformer runtime prepared: {runtime}")
    print("Contents:", ", ".join(sorted(p.name for p in runtime.iterdir())))
    return runtime


def run_prediction(
    *,
    bt_type: str,
    cmode: int,
    nstep: int,
    smiles: str,
    output: Path,
    runtime: Path,
) -> int:
    prepare_runtime(runtime)
    singularity = find_singularity()
    jar = next(runtime.glob("*.jar"))
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    cmd = [
        singularity,
        "exec",
        "--no-mount",
        "cwd,home,tmp",
        "--writable-tmpfs",
        "--pwd",
        "/bt",
        "-B",
        f"{runtime}:/bt",
        "-B",
        f"{output.parent}:/bt-out",
        "-B",
        f"{output.parent}:/tmp",
        "--env",
        "TMPDIR=/tmp",
        "--env",
        "JNA_TMPDIR=/tmp",
        BIOTRANSFORMER_IMAGE,
        "java",
        "-Xms512m",
        "-Xmx6g",
        "-Djava.io.tmpdir=/tmp",
        "-Djna.tmpdir=/tmp",
        "-jar",
        f"/bt/{jar.name}",
        "-b",
        bt_type,
        "-k",
        "pred",
        "-cm",
        str(cmode),
        "-s",
        str(nstep),
        "-ismi",
        smiles,
        "-ocsv",
        f"/bt-out/{output.name}",
    ]
    print("Running:", " ".join(cmd), file=sys.stderr)
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        return completed.returncode

    if not output.is_file() or output.stat().st_size == 0:
        # BioTransformer omits the CSV when there are zero metabolites.
        output.write_text("SMILES\n", encoding="utf-8")
        print(f"WARNING: BioTransformer wrote no CSV; created empty placeholder at {output}", file=sys.stderr)
        return 0

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--runtime", default=DEFAULT_RUNTIME)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("--runtime", default=DEFAULT_RUNTIME)
    run_parser.add_argument("--bt-type", required=True)
    run_parser.add_argument("--cmode", type=int, default=3)
    run_parser.add_argument("--nstep", type=int, default=1)
    run_parser.add_argument("--smiles", required=True)
    run_parser.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    runtime = Path(args.runtime)

    if args.command == "prepare":
        prepare_runtime(runtime)
        return 0

    return run_prediction(
        bt_type=args.bt_type,
        cmode=args.cmode,
        nstep=args.nstep,
        smiles=args.smiles,
        output=Path(args.output),
        runtime=runtime,
    )


if __name__ == "__main__":
    raise SystemExit(main())
