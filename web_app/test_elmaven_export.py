"""Tests for El-MAVEN knowns list export."""

import csv
from pathlib import Path

from elmaven_export import (
    ELMAVEN_FILENAME,
    collect_unique_knowns,
    compound_name,
    export_elmaven_knowns,
    format_pathway_entry,
    load_result_sets,
    normalize_formula,
    transformation_label,
)
from results_viewer import MetaboliteRecord, ResultSet


def _write_compile_tsv(output_dir: Path, molecule_id: str, rows: list[list[str]]) -> None:
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
        "BioTrans_enzyme",
        "BioTrans_system",
        "Figure",
    ]
    tsv_path = output_dir / f"{molecule_id}_CompileResults.tsv"
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)


def test_normalize_formula():
    assert normalize_formula(" C4 H9 NO2 ") == "C4H9NO2"


def test_compound_name_prefers_iupac():
    assert compound_name("ethanol", "Drug", "Figure_1", 1) == "ethanol"
    assert compound_name("Name unavailable", "Drug", "Figure_1", 1) == "Drug_Figure_1"
    assert compound_name("", "Drug", "NA", 2) == "Drug_metabolite_2"
    assert (
        compound_name("ethanol", "Drug", "Figure_1", 1, transformation="Glycine conjugation")
        == "ethanol (Glycine conjugation)"
    )


def test_format_pathway_entry():
    assert format_pathway_entry("Glycine conjugation") == "Glycine conjugation"
    assert format_pathway_entry("glycination_(aliphatic_carboxyl)") == "glycination (aliphatic carboxyl)"


def test_transformation_label_prefers_readable_pathways():
    metabolite = MetaboliteRecord(
        index=1,
        formula="C4H9NO2",
        mass="104.07",
        smiles="N/A",
        iupac="2-Aminobutyrate",
        figure_id="Figure_1",
        image_name="Molecule_1.png",
        sygma_pathway="glycination_(aliphatic_carboxyl);",
        biotrans_pathway="Glycine conjugation",
        gloryx_pathway="glycination_(aliphatic_carboxyl)",
    )
    assert transformation_label(metabolite) == "Glycine conjugation; glycination (aliphatic carboxyl)"


def test_collect_unique_knowns_dedupes_by_formula():
    result_sets = [
        ResultSet(
            id="Drug",
            label="Drug",
            tsv_name="Drug_CompileResults.tsv",
            figure_dir="Drug_figures",
            metabolite_count=2,
            metabolites=[
                MetaboliteRecord(
                    index=1,
                    formula="C4H9NO2",
                    mass="104.07",
                    smiles="N/A",
                    iupac="2-Aminobutyrate",
                    figure_id="Figure_1",
                    image_name="Molecule_1.png",
                    biotrans_pathway="Glycine conjugation",
                ),
                MetaboliteRecord(
                    index=2,
                    formula="C4H9NO2",
                    mass="104.07",
                    smiles="N/A",
                    iupac="GABA",
                    figure_id="Figure_2",
                    image_name="Molecule_2.png",
                ),
                MetaboliteRecord(
                    index=3,
                    formula="C2H6O",
                    mass="47.0",
                    smiles="CCO",
                    iupac="ethanol",
                    figure_id="Figure_3",
                    image_name="Molecule_3.png",
                ),
            ],
        )
    ]

    rows = collect_unique_knowns(result_sets)
    assert len(rows) == 2
    assert {row["formula"] for row in rows} == {"C4H9NO2", "C2H6O"}
    c4_row = next(row for row in rows if row["formula"] == "C4H9NO2")
    assert c4_row["compound"] == "2-Aminobutyrate (Glycine conjugation)"
    assert c4_row["Metabolic.Pathway"] == "Glycine conjugation"
    assert c4_row["mz"] == ""


def test_export_elmaven_knowns_from_output_dir(tmp_path: Path):
    output_dir = tmp_path / "Results_Prediction"
    output_dir.mkdir(parents=True)
    _write_compile_tsv(
        output_dir,
        "Drug",
        [
            [
                "C2H6O",
                "47.0",
                "CCO",
                "ethanol",
                "+",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Figure_1",
            ],
            [
                "C4H9NO2",
                "104.07",
                "N/A",
                "GABA",
                "+",
                "",
                "",
                "",
                "",
                "",
                "Glycine conjugation",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Figure_2",
            ],
        ],
    )

    csv_path = export_elmaven_knowns(output_dir)
    assert csv_path.name == ELMAVEN_FILENAME
    assert csv_path.is_file()

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 2
    assert rows[0]["formula"] == "C2H6O"
    assert rows[0]["compound"] == "ethanol"
    assert rows[0]["mz"] == ""
    assert rows[1]["formula"] == "C4H9NO2"
    assert rows[1]["compound"] == "GABA (Glycine conjugation)"
    assert rows[1]["Metabolic.Pathway"] == "Glycine conjugation"


def test_load_result_sets_reads_tsv(tmp_path: Path):
    output_dir = tmp_path / "Results_Prediction"
    output_dir.mkdir(parents=True)
    _write_compile_tsv(
        output_dir,
        "Drug",
        [["C2H6O", "47.0", "CCO", "ethanol", "+", "", "", "", "", "", "", "", "", "", "", "", "", "", "Figure_1"]],
    )

    result_sets = load_result_sets(output_dir)
    assert len(result_sets) == 1
    assert result_sets[0].metabolites[0].formula == "C2H6O"
