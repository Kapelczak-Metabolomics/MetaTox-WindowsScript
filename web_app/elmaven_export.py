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
    iupac: str,
    molecule_id: str,
    figure_id: str,
    index: int,
    transformation: str = "",
) -> str:
    if not is_missing_iupac(iupac):
        base_name = iupac.strip()
    elif figure_id and figure_id.upper() != "NA":
        base_name = f"{molecule_id}_{figure_id}"
    else:
        base_name = f"{molecule_id}_metabolite_{index}"

    transformation = transformation.strip()
    if transformation:
        return f"{base_name} ({transformation})"
    return base_name


def _name_priority(name: str) -> int:
    lowered = name.lower()
    if lowered.startswith("name unavailable"):
        return 0
    if "_figure_" in lowered or "_metabolite_" in lowered:
        return 1
    return 2


def collect_unique_knowns(result_sets: Iterable[ResultSet]) -> List[Dict[str, str]]:
    """Collect deduplicated known-compound rows keyed by molecular formula."""
    by_formula: Dict[str, Dict[str, str]] = {}

    for result_set in result_sets:
        for metabolite in result_set.metabolites:
            formula = normalize_formula(metabolite.formula)
            if not formula or formula.upper() == "NA":
                continue

            transformation = transformation_label(metabolite)
            name = compound_name(
                metabolite.iupac,
                result_set.id,
                metabolite.figure_id,
                metabolite.index,
                transformation=transformation,
            )
            row = {
                "compound": name,
                "abbrev": "",
                "formula": formula,
                "id": "",
                "mz": "",
                "rt": "",
                "Nr.C": "",
                "Metabolic.Pathway": transformation,
                "Mode": "",
                "Batch": "",
                "": "",
            }

            existing = by_formula.get(formula)
            if existing is None:
                by_formula[formula] = row
                continue

            if _name_priority(name) > _name_priority(existing["compound"]):
                by_formula[formula] = row

    return [by_formula[formula] for formula in sorted(by_formula)]


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
