"""Tests for results viewer parsing."""

import csv
from pathlib import Path

from results_viewer import _figure_to_image_name, load_results_for_viewer


def test_figure_to_image_name():
    assert _figure_to_image_name("Figure_3") == "Molecule_3.png"
    assert _figure_to_image_name("NA") is None


def test_load_results_for_viewer(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "Results_Prediction"
    figures_dir = output_dir / "Drug_figures"
    figures_dir.mkdir(parents=True)
    (figures_dir / "Molecule_1.png").write_bytes(b"png")

    tsv_path = output_dir / "Drug_CompileResults.tsv"
    header = [
        "FormuleBrute",
        "Masse(+H)",
        "Smiles",
        "Iupac",
        "Sygma",
        "BioTransformer3",
        "MetaTrans",
        "GloryX",
        "MetaPredictor",
        "Sygma_pathway",
        "BioTrans_pathway",
        "GloryX_pathway",
        "Sygma_score",
        "GloryX_score",
        "BioTrans_AlogP",
        "BioTrans_precursor",
        "BioTrans_precursor",
        "BioTrans_enzyme",
        "BioTrans_system",
        "Figure",
    ]
    row = [
        "C4H9NO2",
        "104.07",
        "N/A",
        "2-Aminobutyrate",
        "+",
        "+",
        "",
        "+",
        "",
        "glycination_(aliphatic_carboxyl);",
        "Glycine conjugation",
        "glycination_(aliphatic_carboxyl)",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "Figure_1",
    ]
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(header)
        writer.writerow(row)

    monkeypatch.setattr("results_viewer.resolve_iupac_batch", lambda smiles_list, cache_path=None: {"CCO": "ethanol"})
    payload = load_results_for_viewer(output_dir)

    assert payload["available"] is True
    assert len(payload["result_sets"]) == 1
    metabolite = payload["result_sets"][0]["metabolites"][0]
    assert metabolite["iupac"] == "2-Aminobutyrate"
    assert metabolite["image_name"] == "Molecule_1.png"
    assert "BioTransformer3" in metabolite["tools"]
    assert metabolite["sygma_pathway"] == "glycination_(aliphatic_carboxyl);"
    assert metabolite["biotrans_pathway"] == "Glycine conjugation"
    assert metabolite["gloryx_pathway"] == "glycination_(aliphatic_carboxyl)"
