"""Basic tests for the Windows runner helpers."""

from pathlib import Path

import pytest

from metatox_runner import MetaToxOptions, build_shell_command, windows_to_wsl_path


def test_windows_to_wsl_path_drive():
    assert windows_to_wsl_path("C:\\Users\\demo\\input.txt") == "/mnt/c/Users/demo/input.txt"


def test_build_shell_command_contains_required_flags(tmp_path: Path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("Nicotine,CN1CCC[C@H]1c2cccnc2\n", encoding="utf-8")
    root = tmp_path / "MetaTox"
    root.mkdir()
    (root / "Metatox.sh").write_text("#!/usr/bin/bash\n", encoding="utf-8")

    options = MetaToxOptions(
        input_file=str(input_file),
        outdir="Results_Prediction",
        metatox_root=str(root),
        biotrans_type="cyp450",
        predictor_activate=True,
    )
    command = build_shell_command(options)

    assert "--input" in command
    assert "--biotrans 'cyp450'" in command
    assert "--predictor" in command
    assert str(root).replace("\\", "/") in command or "/mnt/" in command
