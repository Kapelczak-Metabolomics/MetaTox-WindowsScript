"""Parse compiled MetaTox results for the interactive viewer."""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from chemistry_utils import smiles_to_iupac


TOOL_COLUMNS = {
    "Sygma": "SygMa",
    "BioTransformer3": "BioTransformer3",
    "MetaTrans": "MetaTrans",
    "GloryX": "GLORYx",
    "MetaPredictor": "Meta-Predictor",
}


@dataclass
class MetaboliteRecord:
    index: int
    formula: str
    mass: str
    smiles: str
    iupac: str
    figure_id: str
    image_name: Optional[str]
    tools: List[str] = field(default_factory=list)
    sygma_pathway: str = ""
    biotrans_pathway: str = ""
    gloryx_pathway: str = ""
    sygma_score: str = ""
    gloryx_score: str = ""
    biotrans_score: str = ""


@dataclass
class ResultSet:
    id: str
    label: str
    tsv_name: str
    figure_dir: str
    metabolite_count: int
    metabolites: List[MetaboliteRecord]


def _figure_to_image_name(figure_id: str) -> Optional[str]:
    if not figure_id or figure_id.upper() == "NA":
        return None
    match = re.fullmatch(r"Figure_(\d+)", figure_id.strip())
    if not match:
        return None
    return f"Molecule_{match.group(1)}.png"


def _active_tools(row: Dict[str, str]) -> List[str]:
    tools: List[str] = []
    for column, label in TOOL_COLUMNS.items():
        value = (row.get(column) or "").strip()
        if value and value != "NA":
            tools.append(label)
    return tools


def _parse_tsv(tsv_path: Path) -> List[MetaboliteRecord]:
    records: List[MetaboliteRecord] = []
    with tsv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for index, row in enumerate(reader, start=1):
            smiles = (row.get("Smiles") or "").strip()
            figure_id = (row.get("Figure") or "").strip()
            iupac = (row.get("Iupac") or row.get("IUPAC") or "").strip()
            if not iupac and smiles:
                iupac = smiles_to_iupac(smiles)

            records.append(
                MetaboliteRecord(
                    index=index,
                    formula=(row.get("FormuleBrute") or "").strip(),
                    mass=(row.get("Masse(+H)") or "").strip(),
                    smiles=smiles,
                    iupac=iupac,
                    figure_id=figure_id,
                    image_name=_figure_to_image_name(figure_id),
                    tools=_active_tools(row),
                    sygma_pathway=(row.get("Sygma_pathway") or "").strip(),
                    biotrans_pathway=(row.get("BioTrans_pathway") or "").strip(),
                    gloryx_pathway=(row.get("GloryX_pathway") or "").strip(),
                    sygma_score=(row.get("Sygma_score") or "").strip(),
                    gloryx_score=(row.get("GloryX_score") or "").strip(),
                    biotrans_score=(row.get("BioTrans_AlogP") or "").strip(),
                )
            )
    return records


def load_results_for_viewer(output_dir: Path) -> Dict[str, object]:
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        return {"available": False, "result_sets": []}

    result_sets: List[ResultSet] = []
    for tsv_path in sorted(output_dir.glob("*_CompileResults.tsv")):
        molecule_id = tsv_path.name.replace("_CompileResults.tsv", "")
        figure_dir = output_dir / f"{molecule_id}_figures"
        metabolites = _parse_tsv(tsv_path)
        result_sets.append(
            ResultSet(
                id=molecule_id,
                label=molecule_id,
                tsv_name=tsv_path.name,
                figure_dir=str(figure_dir),
                metabolite_count=len(metabolites),
                metabolites=metabolites,
            )
        )

    return {
        "available": bool(result_sets),
        "output_dir": str(output_dir),
        "result_sets": [
            {
                **{key: value for key, value in asdict(result_set).items() if key != "metabolites"},
                "metabolites": [asdict(item) for item in result_set.metabolites],
            }
            for result_set in result_sets
        ],
    }


def resolve_result_image(output_dir: Path, molecule_id: str, image_name: str) -> Optional[Path]:
    if not image_name or "/" in image_name or "\\" in image_name or ".." in image_name:
        return None
    if not re.fullmatch(r"Molecule_\d+\.png", image_name):
        return None
    if not re.fullmatch(r"[A-Za-z0-9._-]+", molecule_id):
        return None

    figures_root = (output_dir / f"{molecule_id}_figures").resolve()
    candidate = (figures_root / image_name).resolve()
    if figures_root not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None
