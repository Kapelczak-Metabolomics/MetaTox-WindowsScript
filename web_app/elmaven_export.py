"""Export predicted metabolites to an El-MAVEN / Maven knowns list CSV."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from chemistry_utils import is_missing_iupac
from results_viewer import MetaboliteRecord, ResultSet, _parse_tsv

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


def compound_name(
    iupac: str,
    molecule_id: str,
    figure_id: str,
    index: int,
) -> str:
    if not is_missing_iupac(iupac):
        return iupac.strip()
    if figure_id and figure_id.upper() != "NA":
        return f"{molecule_id}_{figure_id}"
    return f"{molecule_id}_metabolite_{index}"


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

            name = compound_name(
                metabolite.iupac,
                result_set.id,
                metabolite.figure_id,
                metabolite.index,
            )
            row = {
                "compound": name,
                "abbrev": "",
                "formula": formula,
                "id": "",
                "mz": "",
                "rt": "",
                "Nr.C": "",
                "Metabolic.Pathway": "",
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


def load_result_sets(output_dir: Path) -> List[ResultSet]:
    output_dir = output_dir.resolve()
    cache_path = output_dir / ".iupac_cache.json"
    result_sets: List[ResultSet] = []
    for tsv_path in sorted(output_dir.glob("*_CompileResults.tsv")):
        molecule_id = tsv_path.name.replace("_CompileResults.tsv", "")
        metabolites = _parse_tsv(tsv_path, cache_path=cache_path)
        result_sets.append(
            ResultSet(
                id=molecule_id,
                label=molecule_id,
                tsv_name=tsv_path.name,
                figure_dir=str(output_dir / f"{molecule_id}_figures"),
                metabolite_count=len(metabolites),
                metabolites=metabolites,
            )
        )
    return result_sets


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
