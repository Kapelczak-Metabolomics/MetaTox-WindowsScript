"""Tests for the Docker web pipeline helpers."""

from pathlib import Path

import pytest

import zipfile

from pipeline import PipelineOptions, build_command, sanitize_filename, zip_output_directory


def test_sanitize_filename():
    assert sanitize_filename("my input file.txt") == "my_input_file.txt"


def test_build_command_contains_flags(tmp_path: Path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("Nicotine,CN1CCC[C@H]1c2cccnc2\n", encoding="utf-8")
    root = tmp_path / "app"
    root.mkdir()
    (root / "Metatox.sh").write_text("#!/usr/bin/bash\n", encoding="utf-8")

    options = PipelineOptions(
        input_file=input_file,
        biotrans_type="cyp450",
        predictor_activate=True,
        work_dir=root,
    )
    command = build_command(options)

    assert "--input" in command
    assert "--biotrans" in command
    assert "cyp450" in command
    assert "--predictor" in command


def test_zip_output_directory_includes_results(tmp_path: Path):
    output_dir = tmp_path / "results"
    output_dir.mkdir()
    (output_dir / "Nicotine_CompileResults.tsv").write_text("name\tSMILES\n", encoding="utf-8")
    figures = output_dir / "Nicotine_figures"
    figures.mkdir()
    (figures / "plot.png").write_bytes(b"png")

    zip_path = zip_output_directory(output_dir)

    assert zip_path == output_dir / "MetaTox_results.zip"
    assert zip_path.stat().st_size > 0
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert "Nicotine_CompileResults.tsv" in names
    assert "Nicotine_figures/plot.png" in names
    assert "MetaTox_results.zip" not in names


def test_zip_output_directory_requires_compiled_results(tmp_path: Path):
    output_dir = tmp_path / "empty"
    output_dir.mkdir()
    with pytest.raises(RuntimeError, match="No compiled result files"):
        zip_output_directory(output_dir)
