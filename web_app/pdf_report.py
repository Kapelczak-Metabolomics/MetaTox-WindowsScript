"""Generate PDF reports from MetaTox viewer result cards."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from chemistry_utils import is_missing_iupac
from elmaven_export import format_pathway_entry, parse_pathway_entries, transformation_label
from pipeline import get_work_dir
from results_viewer import MetaboliteRecord, ResultSet, load_result_sets, parse_mass_value, resolve_result_image

PDF_FILENAME = "MetaTox_report.pdf"
CARDS_PER_PAGE = 2

COLOR_SLATE_900 = (0.06, 0.09, 0.16)
COLOR_SLATE_700 = (0.20, 0.25, 0.33)
COLOR_SLATE_500 = (0.39, 0.45, 0.55)
COLOR_SLATE_200 = (0.89, 0.91, 0.94)
COLOR_PARENT_BG = (0.94, 0.98, 1.0)
COLOR_PRODUCT_BG = (0.94, 1.0, 0.96)
COLOR_BRAND = (0.15, 0.39, 0.92)


def default_logo_path() -> Path:
    return get_work_dir() / "web_app" / "static" / "img" / "isotopiq-logo.png"


def _sorted_metabolites(metabolites: Iterable[MetaboliteRecord]) -> List[MetaboliteRecord]:
    def sort_key(item: MetaboliteRecord) -> Tuple[float, int]:
        mass_value = parse_mass_value(item.mass)
        return (mass_value if mass_value is not None else float("inf"), item.index)

    return sorted(metabolites, key=sort_key)


def _pathway_lines(metabolite: MetaboliteRecord) -> List[Tuple[str, List[str]]]:
    sections: List[Tuple[str, List[str]]] = []
    for label, value in (
        ("SygMa", metabolite.sygma_pathway),
        ("BioTransformer", metabolite.biotrans_pathway),
        ("GLORYx", metabolite.gloryx_pathway),
    ):
        entries = [format_pathway_entry(entry) for entry in parse_pathway_entries(value)]
        entries = [entry for entry in entries if entry]
        if entries:
            sections.append((label, entries))
    return sections


def _display_iupac(value: str) -> str:
    if is_missing_iupac(value):
        return "Name unavailable"
    return value.strip()


def _safe_image(path: Optional[Path], max_width: float, max_height: float):
    from reportlab.lib.utils import ImageReader

    if path is None or not path.is_file():
        return None

    try:
        image = ImageReader(str(path))
        width, height = image.getSize()
        if width <= 0 or height <= 0:
            return None
        scale = min(max_width / width, max_height / height, 1.0)
        return image, width * scale, height * scale
    except Exception:
        return None


class PdfReportBuilder:
    def __init__(self, destination: Path, logo_path: Optional[Path] = None) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        self.destination = destination.resolve()
        self.logo_path = (logo_path or default_logo_path()).resolve()
        self.page_size = A4
        self.canvas = canvas.Canvas(str(self.destination), pagesize=self.page_size)
        self.width, self.height = self.page_size
        self.margin = 42
        self.header_height = 54
        self.card_gap = 16
        self.cards_on_page = 0
        self.current_molecule = ""
        self.page_initialized = False

    def _usable_height(self) -> float:
        return self.height - (2 * self.margin) - self.header_height

    def _card_height(self) -> float:
        available = self._usable_height()
        return (available - self.card_gap) / CARDS_PER_PAGE

    def _text_width(self, text: str, font_name: str, font_size: int) -> float:
        return self.canvas.stringWidth(text or "", font_name, font_size)

    def _truncate_to_width(self, text: str, font_name: str, font_size: int, max_width: float) -> str:
        cleaned = (text or "—").strip() or "—"
        if self._text_width(cleaned, font_name, font_size) <= max_width:
            return cleaned
        ellipsis = "…"
        trimmed = cleaned
        while trimmed and self._text_width(trimmed + ellipsis, font_name, font_size) > max_width:
            trimmed = trimmed[:-1]
        return (trimmed + ellipsis) if trimmed else ellipsis

    def _wrap_words(self, text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
        words = (text or "—").split()
        if not words:
            return ["—"]

        lines: List[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if self._text_width(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _wrap_characters(self, text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
        cleaned = text or "—"
        lines: List[str] = []
        current = ""
        for character in cleaned:
            candidate = current + character
            if self._text_width(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = character
        if current:
            lines.append(current)
        return lines or ["—"]

    def _draw_header(self, molecule_label: str) -> None:
        top = self.height - self.margin
        if self.logo_path.is_file():
            self.canvas.drawImage(
                str(self.logo_path),
                self.margin,
                top - 34,
                width=92,
                height=28,
                preserveAspectRatio=True,
                mask="auto",
            )

        self.canvas.setFillColorRGB(*COLOR_SLATE_900)
        self.canvas.setFont("Helvetica-Bold", 14)
        self.canvas.drawRightString(self.width - self.margin, top - 16, "MetaTox Prediction Report")

        self.canvas.setFillColorRGB(*COLOR_SLATE_500)
        self.canvas.setFont("Helvetica", 9)
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.canvas.drawRightString(self.width - self.margin, top - 30, generated)

        self.canvas.setFillColorRGB(*COLOR_BRAND)
        self.canvas.setFont("Helvetica-Bold", 11)
        header_label = self._truncate_to_width(
            f"Input molecule: {molecule_label}",
            "Helvetica-Bold",
            11,
            self.width - (2 * self.margin),
        )
        self.canvas.drawString(self.margin, top - 48, header_label)

        self.canvas.setStrokeColorRGB(*COLOR_SLATE_200)
        self.canvas.setLineWidth(1)
        self.canvas.line(self.margin, top - 54, self.width - self.margin, top - 54)

    def _new_page(self, molecule_label: str) -> None:
        if self.page_initialized:
            self.canvas.showPage()
        self.page_initialized = True
        self.cards_on_page = 0
        self.current_molecule = molecule_label
        self._draw_header(molecule_label)

    def _ensure_page(self, molecule_label: str) -> None:
        if not self.page_initialized:
            self._new_page(molecule_label)
            return
        if self.cards_on_page >= CARDS_PER_PAGE or molecule_label != self.current_molecule:
            self._new_page(molecule_label)

    def _draw_wrapped_text(
        self,
        text: str,
        x: float,
        y: float,
        width: float,
        font_name: str,
        font_size: int,
        color: Tuple[float, float, float],
        max_lines: int = 6,
        monospace: bool = False,
    ) -> float:
        self.canvas.setFillColorRGB(*color)
        self.canvas.setFont(font_name, font_size)
        lines = (
            self._wrap_characters(text, font_name, font_size, width)
            if monospace
            else self._wrap_words(text, font_name, font_size, width)
        )
        line_height = font_size + 3
        cursor_y = y
        for line in lines[:max_lines]:
            clipped = self._truncate_to_width(line, font_name, font_size, width)
            self.canvas.drawString(x, cursor_y, clipped)
            cursor_y -= line_height
        if len(lines) > max_lines:
            self.canvas.drawString(x, cursor_y, "…")
            cursor_y -= line_height
        return cursor_y

    def _draw_structure_panel(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        title: str,
        caption: str,
        formula: str,
        mass: str,
        image_path: Optional[Path],
        background: Tuple[float, float, float],
    ) -> None:
        inner_width = max(width - 20, 40)
        self.canvas.setFillColorRGB(1, 1, 1)
        self.canvas.setStrokeColorRGB(*COLOR_SLATE_200)
        self.canvas.roundRect(x, y, width, height, 8, stroke=1, fill=1)

        self.canvas.setFillColorRGB(*COLOR_SLATE_500)
        self.canvas.setFont("Helvetica-Bold", 7)
        self.canvas.drawString(x + 10, y + height - 14, title.upper())

        box_y = y + 34
        box_height = height - 78
        self.canvas.setFillColorRGB(*background)
        self.canvas.setStrokeColorRGB(*COLOR_SLATE_200)
        self.canvas.roundRect(x + 10, box_y, inner_width, box_height, 6, stroke=1, fill=1)

        image_data = _safe_image(image_path, inner_width - 8, box_height - 12)
        if image_data:
            image, image_width, image_height = image_data
            image_x = x + 10 + (inner_width - image_width) / 2
            image_y = box_y + (box_height - image_height) / 2
            self.canvas.drawImage(image, image_x, image_y, width=image_width, height=image_height, mask="auto")
        else:
            self.canvas.setFillColorRGB(*COLOR_SLATE_500)
            self.canvas.setFont("Helvetica", 8)
            self.canvas.drawCentredString(x + width / 2, box_y + box_height / 2, "No structure image")

        self.canvas.setFillColorRGB(*COLOR_SLATE_900)
        self.canvas.setFont("Helvetica-Bold", 8)
        self.canvas.drawString(
            x + 10,
            y + 22,
            self._truncate_to_width(caption or "—", "Helvetica-Bold", 8, inner_width),
        )

        self.canvas.setFillColorRGB(*COLOR_SLATE_700)
        self.canvas.setFont("Helvetica", 7)
        self.canvas.drawString(
            x + 10,
            y + 12,
            self._truncate_to_width(f"Formula: {formula or 'NA'}", "Helvetica", 7, inner_width),
        )
        self.canvas.drawString(
            x + 10,
            y + 4,
            self._truncate_to_width(f"Mass (+H): {mass or 'NA'}", "Helvetica", 7, inner_width),
        )

    def _draw_card(
        self,
        output_dir: Path,
        result_set: ResultSet,
        metabolite: MetaboliteRecord,
    ) -> None:
        self._ensure_page(result_set.label)
        card_height = self._card_height()
        card_top = self.height - self.margin - self.header_height - (self.cards_on_page * (card_height + self.card_gap))
        card_y = card_top - card_height
        card_x = self.margin
        card_width = self.width - (2 * self.margin)
        card_right = card_x + card_width
        min_content_y = card_y + 12

        self.canvas.setFillColorRGB(1, 1, 1)
        self.canvas.setStrokeColorRGB(*COLOR_SLATE_200)
        self.canvas.roundRect(card_x, card_y, card_width, card_height, 10, stroke=1, fill=1)

        structure_width = card_width * 0.42
        details_x = card_x + structure_width + 14
        details_width = max(card_right - details_x - 12, 120)
        inner_y = card_y + 12
        inner_height = card_height - 24

        parent = result_set.parent
        parent_image = resolve_result_image(output_dir, result_set.id, parent.image_name) if parent and parent.image_name else None
        product_image = (
            resolve_result_image(output_dir, result_set.id, metabolite.image_name) if metabolite.image_name else None
        )

        panel_width = max((structure_width - 30) / 2, 70)
        self._draw_structure_panel(
            card_x + 12,
            inner_y,
            panel_width,
            inner_height,
            "Original molecule",
            parent.name if parent else result_set.label,
            parent.formula if parent else "",
            parent.mass if parent else "",
            parent_image,
            COLOR_PARENT_BG,
        )

        arrow_x = card_x + 12 + panel_width + 4
        self.canvas.setFillColorRGB(*COLOR_SLATE_500)
        self.canvas.setFont("Helvetica-Bold", 12)
        self.canvas.drawCentredString(arrow_x + 11, inner_y + inner_height / 2, "→")

        self._draw_structure_panel(
            card_x + 12 + panel_width + 26,
            inner_y,
            panel_width,
            inner_height,
            "Predicted product",
            metabolite.figure_id or f"Metabolite {metabolite.index}",
            metabolite.formula,
            metabolite.mass,
            product_image,
            COLOR_PRODUCT_BG,
        )

        title = metabolite.figure_id or f"Metabolite {metabolite.index}"
        self.canvas.setFillColorRGB(*COLOR_SLATE_900)
        self.canvas.setFont("Helvetica-Bold", 12)
        self.canvas.drawString(
            details_x,
            card_y + card_height - 22,
            self._truncate_to_width(title, "Helvetica-Bold", 12, details_width - 36),
        )
        self.canvas.setFillColorRGB(*COLOR_SLATE_500)
        self.canvas.setFont("Helvetica", 9)
        self.canvas.drawRightString(card_right - 12, card_y + card_height - 22, f"#{metabolite.index}")

        cursor_y = card_y + card_height - 38
        cursor_y = self._draw_wrapped_text(
            f"IUPAC: {_display_iupac(metabolite.iupac)}",
            details_x,
            cursor_y,
            details_width,
            "Helvetica",
            8,
            COLOR_SLATE_700,
            max_lines=3,
        ) - 4

        if cursor_y >= min_content_y:
            formula_text = self._truncate_to_width(
                f"Formula: {metabolite.formula or 'NA'}",
                "Helvetica",
                8,
                details_width / 2 - 4,
            )
            mass_text = self._truncate_to_width(
                f"Mass (+H): {metabolite.mass or 'NA'}",
                "Helvetica",
                8,
                details_width / 2 - 4,
            )
            self.canvas.setFillColorRGB(*COLOR_SLATE_700)
            self.canvas.setFont("Helvetica", 8)
            self.canvas.drawString(details_x, cursor_y, formula_text)
            self.canvas.drawString(details_x + details_width / 2, cursor_y, mass_text)
            cursor_y -= 14

        if cursor_y >= min_content_y:
            cursor_y = self._draw_wrapped_text(
                f"SMILES: {metabolite.smiles or '—'}",
                details_x,
                cursor_y,
                details_width,
                "Courier",
                7,
                COLOR_SLATE_700,
                max_lines=2,
                monospace=True,
            ) - 4

        if cursor_y >= min_content_y and metabolite.tools:
            self.canvas.setFillColorRGB(*COLOR_BRAND)
            self.canvas.setFont("Helvetica-Bold", 7)
            self.canvas.drawString(
                details_x,
                cursor_y,
                self._truncate_to_width(" · ".join(metabolite.tools), "Helvetica-Bold", 7, details_width),
            )
            cursor_y -= 12

        if cursor_y >= min_content_y and _pathway_lines(metabolite):
            self.canvas.setFillColorRGB(*COLOR_SLATE_500)
            self.canvas.setFont("Helvetica-Bold", 7)
            self.canvas.drawString(details_x, cursor_y, "PREDICTED TRANSFORMATIONS")
            cursor_y -= 10
            for source, entries in _pathway_lines(metabolite):
                if cursor_y < min_content_y:
                    break
                self.canvas.setFillColorRGB(*COLOR_SLATE_700)
                self.canvas.setFont("Helvetica-Bold", 7)
                self.canvas.drawString(
                    details_x + 4,
                    cursor_y,
                    self._truncate_to_width(source, "Helvetica-Bold", 7, details_width - 8),
                )
                cursor_y -= 9
                for entry in entries[:2]:
                    if cursor_y < min_content_y:
                        break
                    cursor_y = self._draw_wrapped_text(
                        f"• {entry}",
                        details_x + 8,
                        cursor_y,
                        details_width - 12,
                        "Helvetica",
                        7,
                        COLOR_SLATE_700,
                        max_lines=2,
                    ) - 2

        self.cards_on_page += 1

    def save(self) -> Path:
        self.canvas.save()
        return self.destination


def export_pdf_report(
    output_dir: Path,
    destination: Optional[Path] = None,
    molecule_id: Optional[str] = None,
    metabolite_indices: Optional[Sequence[int]] = None,
    logo_path: Optional[Path] = None,
) -> Path:
    output_dir = output_dir.resolve()
    result_sets = load_result_sets(output_dir)
    if not result_sets:
        raise RuntimeError(f"No compiled results were found in {output_dir}.")

    if molecule_id:
        result_sets = [item for item in result_sets if item.id == molecule_id]
        if not result_sets:
            raise RuntimeError(f"No results were found for molecule '{molecule_id}'.")

    allowed_indices = set(metabolite_indices) if metabolite_indices is not None else None
    target = destination or (output_dir / PDF_FILENAME)
    builder = PdfReportBuilder(target, logo_path=logo_path)
    card_count = 0

    for result_set in result_sets:
        metabolites = _sorted_metabolites(result_set.metabolites)
        if allowed_indices is not None:
            metabolites = [item for item in metabolites if item.index in allowed_indices]
        for metabolite in metabolites:
            builder._draw_card(output_dir, result_set, metabolite)
            card_count += 1

    if card_count == 0:
        raise RuntimeError("No metabolite cards were available to export.")

    return builder.save()


def export_pdf_report_bytes(
    output_dir: Path,
    molecule_id: Optional[str] = None,
    metabolite_indices: Optional[Sequence[int]] = None,
    logo_path: Optional[Path] = None,
) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        path = Path(handle.name)
        export_pdf_report(
            output_dir,
            destination=path,
            molecule_id=molecule_id,
            metabolite_indices=metabolite_indices,
            logo_path=logo_path,
        )
        return path.read_bytes()


def pdf_report_path(output_dir: Path) -> Path:
    return output_dir.resolve() / PDF_FILENAME
