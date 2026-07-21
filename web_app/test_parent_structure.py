"""Tests for parent structure rendering and viewer metadata."""

from pathlib import Path

import pytest

from results_viewer import (
    ensure_parent_structure,
    ensure_parent_structures,
    load_parent_structure,
    load_results_for_viewer,
    parse_input_molecules,
    resolve_result_image,
)
from structure_renderer import PARENT_IMAGE_NAME, PARENT_META_NAME, render_smiles_to_png


def test_parse_input_molecules(tmp_path: Path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("Nicotine,CN1CCC[C@H]1c2cccnc2\nAspirin,CC(=O)Oc1ccccc1C(=O)O\n", encoding="utf-8")

    molecules = parse_input_molecules(input_file)
    assert set(molecules) == {"Nicotine", "Aspirin"}
    assert molecules["Nicotine"]["smiles"] == "CN1CCC[C@H]1c2cccnc2"


def test_render_smiles_to_png(tmp_path: Path):
    destination = tmp_path / "Input.png"
    assert render_smiles_to_png("CCO", destination) is True
    assert destination.is_file()
    assert destination.stat().st_size > 0


def test_ensure_parent_structure_writes_metadata_and_image(tmp_path: Path):
    output_dir = tmp_path / "Results_Prediction"
    parent = {"name": "Drug", "smiles": "CCO"}

    result = ensure_parent_structure(output_dir, "Drug", parent)
    assert result is not None
    assert result.image_name == PARENT_IMAGE_NAME
    assert result.formula

    figures_dir = output_dir / "Drug_figures"
    assert (figures_dir / PARENT_IMAGE_NAME).is_file()
    assert (figures_dir / PARENT_META_NAME).is_file()


def test_load_results_for_viewer_includes_parent(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "Results_Prediction"
    figures_dir = output_dir / "Drug_figures"
    figures_dir.mkdir(parents=True)
    (figures_dir / "Molecule_1.png").write_bytes(b"png")
    ensure_parent_structure(output_dir, "Drug", {"name": "Drug", "smiles": "CCO"})

    tsv_path = output_dir / "Drug_CompileResults.tsv"
    tsv_path.write_text(
        "FormuleBrute\tMasse(+H)\tSmiles\tIupac\tSygma\tBioTransformer3\tMetaTrans\tGloryX\tMetaPredictor\tFigure\n"
        "C2H6O\t47.0\tCCO\tethanol\t+\t+\t\t\t\tFigure_1\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("results_viewer.resolve_iupac_batch", lambda smiles_list, cache_path=None: {})
    payload = load_results_for_viewer(output_dir)

    parent = payload["result_sets"][0]["parent"]
    assert parent is not None
    assert parent["name"] == "Drug"
    assert parent["image_name"] == PARENT_IMAGE_NAME
    assert parent["smiles"] == "CCO"


def test_resolve_result_image_allows_parent_image(tmp_path: Path):
    output_dir = tmp_path / "Results_Prediction"
    figures_dir = output_dir / "Drug_figures"
    figures_dir.mkdir(parents=True)
    image_path = figures_dir / PARENT_IMAGE_NAME
    image_path.write_bytes(b"png")

    resolved = resolve_result_image(output_dir, "Drug", PARENT_IMAGE_NAME)
    assert resolved == image_path.resolve()


def test_ensure_parent_structures_from_input_file(tmp_path: Path):
    output_dir = tmp_path / "Results_Prediction"
    output_dir.mkdir(parents=True)
    (output_dir / "Nicotine_CompileResults.tsv").write_text("Figure\nFigure_1\n", encoding="utf-8")

    input_file = tmp_path / "input.txt"
    input_file.write_text("Nicotine,CN1CCC[C@H]1c2cccnc2\n", encoding="utf-8")

    ensure_parent_structures(output_dir, input_file)
    parent = load_parent_structure(output_dir, "Nicotine")
    assert parent is not None
    assert parent.image_name == PARENT_IMAGE_NAME
