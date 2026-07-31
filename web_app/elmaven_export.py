"""Export predicted metabolites to an El-MAVEN / Maven knowns list CSV."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from chemistry_utils import is_missing_iupac
from results_viewer import MetaboliteRecord, ResultSet, _parse_tsv, load_result_sets

ELMAVEN_FILENAME = "MetaTox_elmaven_knowns.csv"
ELMAVEN_COLUMNS = [
    "compound",
    "abbrev",
    "formula",
    "id",
    "mz",
    "rt",
    "Nr.C",
    "Metabolic.Pathway",
    "Mode",
    "Batch",
    "",
]


def normalize_formula(formula: str) -> str:
    return re.sub(r"\s+", "", (formula or "").strip())


def parse_pathway_entries(value: str) -> List[str]:
    entries: List[str] = []
    for raw_entry in (value or "").split(";"):
        entry = raw_entry.strip().rstrip(";,").strip()
        if entry and entry.upper() != "NA":
            entries.append(entry)
    return entries


def format_pathway_entry(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if any(character.isupper() for character in cleaned) and " " in cleaned:
        return cleaned
    return cleaned.replace("_", " ")


def transformation_label(metabolite: MetaboliteRecord) -> str:
    candidates: List[str] = []
    for value in (
        metabolite.biotrans_pathway,
        metabolite.gloryx_pathway,
        metabolite.sygma_pathway,
    ):
        for entry in parse_pathway_entries(value):
            formatted = format_pathway_entry(entry)
            if formatted and formatted not in candidates:
                candidates.append(formatted)

    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]
    return "; ".join(candidates[:2])


def compound_name(
    molecule_label: str,
    figure_id: str,
    index: int,
    transformation: str = "",
) -> str:
    label = (molecule_label or "").strip() or "compound"
    if figure_id and figure_id.upper() != "NA":
        stem = f"{label}_{figure_id}"
    else:
        stem = f"{label}_metabolite_{index}"

    transformation = transformation.strip()
    if transformation:
        return f"{stem} ({transformation})"
    return stem


def compound_abbrev(iupac: str) -> str:
    if is_missing_iupac(iupac):
        return ""
    return iupac.strip()


def _row_sort_key(row: Dict[str, str]) -> tuple:
    mass_value = row.get("mz") or ""
    try:
        mass_number = float(mass_value)
    except ValueError:
        mass_number = float("inf")
    return (row.get("_molecule", ""), mass_number, int(row.get("_index", "0")))


def collect_unique_knowns(result_sets: Iterable[ResultSet]) -> List[Dict[str, str]]:
    """Collect one El-MAVEN row per predicted metabolite."""
    rows: List[Dict[str, str]] = []
    seen: set[tuple[str, int]] = set()

    for result_set in result_sets:
        molecule_label = (result_set.label or result_set.id or "").strip() or result_set.id
        for metabolite in result_set.metabolites:
            formula = normalize_formula(metabolite.formula)
            if not formula or formula.upper() == "NA":
                continue

            dedupe_key = (result_set.id, metabolite.index)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            transformation = transformation_label(metabolite)
            name = compound_name(
                molecule_label,
                metabolite.figure_id,
                metabolite.index,
                transformation=transformation,
            )
            rows.append(
                {
                    "compound": name,
                    "abbrev": compound_abbrev(metabolite.iupac),
                    "formula": formula,
                    "id": metabolite.figure_id if metabolite.figure_id.upper() != "NA" else "",
                    "mz": (metabolite.mass or "").strip(),
                    "rt": "",
                    "Nr.C": "",
                    "Metabolic.Pathway": transformation,
                    "Mode": "",
                    "Batch": "",
                    "": "",
                    "_molecule": molecule_label,
                    "_index": str(metabolite.index),
                }
            )

    sortable_rows = sorted(rows, key=_row_sort_key)
    return [{key: value for key, value in row.items() if not key.startswith("_")} for row in sortable_rows]


def write_elmaven_knowns(rows: List[Dict[str, str]], destination: Path) -> Path:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ELMAVEN_COLUMNS,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return destination


def export_elmaven_knowns(output_dir: Path, destination: Optional[Path] = None) -> Path:
    output_dir = output_dir.resolve()
    result_sets = load_result_sets(output_dir)
    if not result_sets:
        raise RuntimeError(f"No compiled results were found in {output_dir}.")

    rows = collect_unique_knowns(result_sets)
    target = destination or (output_dir / ELMAVEN_FILENAME)
    return write_elmaven_knowns(rows, target)


def elmaven_knowns_path(output_dir: Path) -> Path:
    return output_dir.resolve() / ELMAVEN_FILENAME
