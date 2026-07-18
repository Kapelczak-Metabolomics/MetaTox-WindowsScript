"""Tests for the Docker web pipeline helpers."""

from pathlib import Path

import pytest

from pipeline import PipelineOptions, build_command, sanitize_filename


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
