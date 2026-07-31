"""Tests for pasted input handling."""

from pathlib import Path

import pytest

from app import _resolve_input_path, _save_pasted_input


def test_save_pasted_input(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    path = _save_pasted_input("Nicotine,CN1CCC[C@H]1c2cccnc2")
    assert path.is_file()
    assert "Nicotine" in path.read_text(encoding="utf-8")


def test_save_pasted_input_rejects_empty():
    with pytest.raises(ValueError, match="Paste at least one"):
        _save_pasted_input("   ")


def test_save_pasted_input_rejects_invalid_format(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="MoleculeName,SMILES"):
        _save_pasted_input("invalid-line-without-comma")
