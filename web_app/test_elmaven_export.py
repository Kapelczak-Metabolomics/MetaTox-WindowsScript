"""Tests for El-MAVEN knowns list export."""

import csv
from pathlib import Path

from elmaven_export import (
    ELMAVEN_FILENAME,
    collect_unique_knowns,
    compound_abbrev,
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


def test_compound_name_includes_molecule_figure_and_transformation():
    assert compound_name("JNJ-40418677", "Figure_171", 171) == "JNJ-40418677_Figure_171"
    assert compound_name("Drug", "Figure_1", 1) == "Drug_Figure_1"
    assert compound_name("Drug", "NA", 2) == "Drug_metabolite_2"
    assert (
        compound_name("JNJ-40418677", "Figure_171", 171, transformation="alpha-Hydroxylation of carbonyl group")
        == "JNJ-40418677_Figure_171 (alpha-Hydroxylation of carbonyl group)"
    )
    assert (
        compound_name("Drug", "Figure_1", 1, transformation="Glycine conjugation")
        == "Drug_Figure_1 (Glycine conjugation)"
    )


def test_compound_abbrev_uses_iupac():
    assert compound_abbrev("ethanol") == "ethanol"
    assert compound_abbrev("Name unavailable") == ""
    assert compound_abbrev("") == ""


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


def test_collect_unique_knowns_keeps_distinct_metabolites_with_same_formula():
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
                    biotrans_pathway="Oxidation",
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
    assert len(rows) == 3
    assert {row["formula"] for row in rows} == {"C4H9NO2", "C2H6O"}
    figure_1 = next(row for row in rows if row["id"] == "Figure_1")
    figure_2 = next(row for row in rows if row["id"] == "Figure_2")
    assert figure_1["compound"] == "Drug_Figure_1 (Glycine conjugation)"
    assert figure_1["abbrev"] == "2-Aminobutyrate"
    assert figure_1["Metabolic.Pathway"] == "Glycine conjugation"
    assert figure_1["mz"] == "104.07"
    assert figure_2["compound"] == "Drug_Figure_2 (Oxidation)"
    assert figure_2["abbrev"] == "GABA"


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
    ethanol_row = next(row for row in rows if row["formula"] == "C2H6O")
    gaba_row = next(row for row in rows if row["formula"] == "C4H9NO2")
    assert ethanol_row["compound"] == "Drug_Figure_1"
    assert ethanol_row["abbrev"] == "ethanol"
    assert ethanol_row["mz"] == "47.0"
    assert gaba_row["compound"] == "Drug_Figure_2 (Glycine conjugation)"
    assert gaba_row["abbrev"] == "GABA"
    assert gaba_row["Metabolic.Pathway"] == "Glycine conjugation"


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
