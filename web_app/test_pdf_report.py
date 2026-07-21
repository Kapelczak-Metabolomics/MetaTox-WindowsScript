"""Tests for PDF report export."""

import csv
from pathlib import Path

import pytest

from pdf_report import PDF_FILENAME, export_pdf_report
from results_viewer import ensure_parent_structure
from structure_renderer import PARENT_IMAGE_NAME


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


def test_export_pdf_report_creates_pdf(tmp_path: Path):
    pytest.importorskip("reportlab")

    output_dir = tmp_path / "Results_Prediction"
    figures_dir = output_dir / "Drug_figures"
    figures_dir.mkdir(parents=True)
    (figures_dir / "Molecule_1.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    ensure_parent_structure(output_dir, "Drug", {"name": "Drug", "smiles": "CCO"})
    parent_image = figures_dir / PARENT_IMAGE_NAME
    if not parent_image.is_file():
        (figures_dir / PARENT_IMAGE_NAME).write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
        )

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
                "Glycine conjugation",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Figure_1",
            ],
        ],
    )

    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    pdf_path = export_pdf_report(output_dir, logo_path=logo_path)
    assert pdf_path.name == PDF_FILENAME
    assert pdf_path.is_file()
    assert pdf_path.stat().st_size > 500
    assert pdf_path.read_bytes()[:4] == b"%PDF"


def test_export_pdf_report_requires_results(tmp_path: Path):
    pytest.importorskip("reportlab")
    with pytest.raises(RuntimeError, match="No compiled results"):
        export_pdf_report(tmp_path / "missing")
