"""Tests for zip extraction used by the results viewer."""

import zipfile
from pathlib import Path

import pytest

from pipeline import extract_results_zip, zip_output_directory


def test_extract_results_zip_round_trip(tmp_path: Path):
    output_dir = tmp_path / "Results_Prediction"
    figures_dir = output_dir / "Drug_figures"
    figures_dir.mkdir(parents=True)
    (figures_dir / "Molecule_1.png").write_bytes(b"png")
    (output_dir / "Drug_CompileResults.tsv").write_text("FormuleBrute\tMasse(+H)\n", encoding="utf-8")

    archive_path = zip_output_directory(output_dir)
    destination = tmp_path / "uploaded"
    extracted = extract_results_zip(archive_path, destination)

    assert extracted == destination.resolve()
    assert (destination / "Drug_CompileResults.tsv").is_file()
    assert (destination / "Drug_figures" / "Molecule_1.png").is_file()


def test_extract_results_zip_rejects_unsafe_paths(tmp_path: Path):
    archive_path = tmp_path / "unsafe.zip"
    destination = tmp_path / "uploaded"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "nope")

    with pytest.raises(ValueError, match="Unsafe path"):
        extract_results_zip(archive_path, destination)
