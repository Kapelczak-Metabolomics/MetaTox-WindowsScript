"""Tests for PDF report export."""

import csv
import re
from pathlib import Path

import pytest

from pdf_report import PDF_FILENAME, export_pdf_report, export_pdf_report_bytes
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


def _pdf_fixture(tmp_path: Path) -> tuple[Path, Path]:
    output_dir = tmp_path / "Results_Prediction"
    figures_dir = output_dir / "Drug_figures"
    figures_dir.mkdir(parents=True)
    image_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (figures_dir / "Molecule_1.png").write_bytes(image_bytes)
    (figures_dir / "Molecule_2.png").write_bytes(image_bytes)
    ensure_parent_structure(output_dir, "Drug", {"name": "Drug", "smiles": "CCO"})
    parent_image = figures_dir / PARENT_IMAGE_NAME
    if not parent_image.is_file():
        parent_image.write_bytes(image_bytes)

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
            [
                "C3H8O",
                "61.0",
                "CCCO",
                "propanol",
                "",
                "+",
                "",
                "",
                "",
                "",
                "",
                "Hydroxylation",
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

    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(image_bytes)
    return output_dir, logo_path


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf_bytes))


def test_export_pdf_report_filters_selected_indices(tmp_path: Path):
    pytest.importorskip("reportlab")

    output_dir, logo_path = _pdf_fixture(tmp_path)
    full_pdf = export_pdf_report_bytes(output_dir, molecule_id="Drug", logo_path=logo_path)
    selected_pdf = export_pdf_report_bytes(
        output_dir,
        molecule_id="Drug",
        metabolite_indices=[2],
        logo_path=logo_path,
    )

    assert selected_pdf.startswith(b"%PDF")
    assert len(selected_pdf) < len(full_pdf)


def test_export_pdf_report_rejects_empty_selection(tmp_path: Path):
    pytest.importorskip("reportlab")

    output_dir, logo_path = _pdf_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="No metabolite cards were available"):
        export_pdf_report(output_dir, molecule_id="Drug", metabolite_indices=[], logo_path=logo_path)


def test_export_pdf_report_single_card_has_one_page(tmp_path: Path):
    pytest.importorskip("reportlab")

    output_dir, logo_path = _pdf_fixture(tmp_path)
    pdf_bytes = export_pdf_report_bytes(
        output_dir,
        molecule_id="Drug",
        metabolite_indices=[1],
        logo_path=logo_path,
    )

    assert _count_pdf_pages(pdf_bytes) == 1
