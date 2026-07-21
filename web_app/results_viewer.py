"""Parse compiled MetaTox results for the interactive viewer."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from chemistry_utils import (
    is_missing_iupac,
    load_iupac_cache,
    resolve_iupac_batch,
)
from structure_renderer import (
    PARENT_IMAGE_NAME,
    PARENT_META_NAME,
    render_smiles_to_png,
    smiles_formula_and_mass,
)


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
class ParentStructure:
    name: str
    smiles: str
    image_name: Optional[str] = None
    formula: str = ""
    mass: str = ""


@dataclass
class ResultSet:
    id: str
    label: str
    tsv_name: str
    figure_dir: str
    metabolite_count: int
    metabolites: List[MetaboliteRecord]
    parent: Optional[ParentStructure] = None


def parse_input_molecules(input_file: Path) -> Dict[str, Dict[str, str]]:
    molecules: Dict[str, Dict[str, str]] = {}
    if not input_file.is_file():
        return molecules

    with input_file.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(",", 1)
            if len(parts) != 2:
                continue
            name, smiles = parts[0].strip(), parts[1].strip()
            if not name or not smiles:
                continue
            molecules[name] = {"name": name, "smiles": smiles}
    return molecules


def _write_parent_metadata(figures_dir: Path, parent: Dict[str, str], formula: str, mass: str) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": parent["name"],
        "smiles": parent["smiles"],
        "formula": formula,
        "mass": mass,
    }
    (figures_dir / PARENT_META_NAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_parent_structure(
    output_dir: Path,
    molecule_id: str,
    parent: Dict[str, str],
) -> Optional[ParentStructure]:
    figures_dir = output_dir / f"{molecule_id}_figures"
    formula, mass = smiles_formula_and_mass(parent["smiles"])
    image_path = figures_dir / PARENT_IMAGE_NAME

    if not image_path.is_file():
        render_smiles_to_png(parent["smiles"], image_path)

    _write_parent_metadata(figures_dir, parent, formula, mass)

    if not image_path.is_file():
        return ParentStructure(
            name=parent["name"],
            smiles=parent["smiles"],
            image_name=None,
            formula=formula,
            mass=mass,
        )

    return ParentStructure(
        name=parent["name"],
        smiles=parent["smiles"],
        image_name=PARENT_IMAGE_NAME,
        formula=formula,
        mass=mass,
    )


def ensure_parent_structures(output_dir: Path, input_file: Optional[Path] = None) -> None:
    if input_file is None or not input_file.is_file():
        return

    molecules = parse_input_molecules(input_file)
    if not molecules:
        return

    output_dir = output_dir.resolve()
    for tsv_path in sorted(output_dir.glob("*_CompileResults.tsv")):
        molecule_id = tsv_path.name.replace("_CompileResults.tsv", "")
        parent = molecules.get(molecule_id)
        if parent:
            ensure_parent_structure(output_dir, molecule_id, parent)


def load_parent_structure(output_dir: Path, molecule_id: str) -> Optional[ParentStructure]:
    figures_dir = output_dir / f"{molecule_id}_figures"
    meta_path = figures_dir / PARENT_META_NAME
    image_path = figures_dir / PARENT_IMAGE_NAME

    if meta_path.is_file():
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}

        smiles = (payload.get("smiles") or "").strip()
        name = (payload.get("name") or molecule_id).strip()
        if smiles and not image_path.is_file():
            render_smiles_to_png(smiles, image_path)

        return ParentStructure(
            name=name or molecule_id,
            smiles=smiles,
            image_name=PARENT_IMAGE_NAME if image_path.is_file() else None,
            formula=(payload.get("formula") or "").strip(),
            mass=(payload.get("mass") or "").strip(),
        )

    if image_path.is_file():
        return ParentStructure(
            name=molecule_id,
            smiles="",
            image_name=PARENT_IMAGE_NAME,
        )

    return None


def parent_to_dict(parent: Optional[ParentStructure]) -> Optional[Dict[str, object]]:
    if parent is None:
        return None
    return asdict(parent)


def _figure_to_image_name(figure_id: str) -> Optional[str]:
    if not figure_id or figure_id.upper() == "NA":
        return None
    match = re.fullmatch(r"Figure_(\d+)", figure_id.strip())
    if not match:
        return None
    return f"Molecule_{match.group(1)}.png"


def parse_mass_value(mass: str) -> Optional[float]:
    cleaned = (mass or "").strip()
    if not cleaned or cleaned.upper() == "NA":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def mass_group_key(mass: str) -> str:
    value = parse_mass_value(mass)
    if value is None:
        return "na"
    return f"{value:.5f}"


def _active_tools(row: Dict[str, str]) -> List[str]:
    tools: List[str] = []
    for column, label in TOOL_COLUMNS.items():
        value = (row.get(column) or "").strip()
        if value and value != "NA":
            tools.append(label)
    return tools


def _parse_tsv(
    tsv_path: Path,
    cache_path: Optional[Path] = None,
    resolve_missing: bool = False,
) -> List[MetaboliteRecord]:
    records: List[MetaboliteRecord] = []
    pending_smiles: List[str] = []
    pending_rows: List[dict] = []
    cache = load_iupac_cache(cache_path) if cache_path else {}

    with tsv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for index, row in enumerate(reader, start=1):
            smiles = (row.get("Smiles") or "").strip()
            figure_id = (row.get("Figure") or "").strip()
            iupac = (row.get("Iupac") or row.get("IUPAC") or "").strip()
            pending_rows.append(
                {
                    "index": index,
                    "row": row,
                    "smiles": smiles,
                    "figure_id": figure_id,
                    "iupac": iupac,
                }
            )
            if is_missing_iupac(iupac) and smiles:
                pending_smiles.append(smiles)

    resolved_names: Dict[str, str] = {}
    if resolve_missing:
        resolved_names = resolve_iupac_batch(pending_smiles, cache_path=cache_path)
    else:
        resolved_names = {
            smiles: cache[smiles]
            for smiles in pending_smiles
            if smiles in cache and not is_missing_iupac(cache[smiles])
        }

    for item in pending_rows:
        smiles = item["smiles"]
        iupac = item["iupac"]
        if is_missing_iupac(iupac) and smiles:
            iupac = resolved_names.get(smiles, "")

        row = item["row"]
        records.append(
            MetaboliteRecord(
                index=item["index"],
                formula=(row.get("FormuleBrute") or "").strip(),
                mass=(row.get("Masse(+H)") or "").strip(),
                smiles=smiles,
                iupac=iupac,
                figure_id=item["figure_id"],
                image_name=_figure_to_image_name(item["figure_id"]),
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


def metabolite_to_dict(record: MetaboliteRecord) -> Dict[str, object]:
    payload = asdict(record)
    payload["mass_value"] = parse_mass_value(record.mass)
    payload["mass_group"] = mass_group_key(record.mass)
    return payload


def resolve_iupac_for_smiles(output_dir: Path, smiles_list: List[str]) -> Dict[str, str]:
    output_dir = output_dir.resolve()
    return resolve_iupac_batch(smiles_list, cache_path=output_dir / ".iupac_cache.json")


def load_results_for_viewer(output_dir: Path) -> Dict[str, object]:
    output_dir = output_dir.resolve()
    if not output_dir.is_dir():
        return {"available": False, "result_sets": []}

    result_sets: List[ResultSet] = []
    for tsv_path in sorted(output_dir.glob("*_CompileResults.tsv")):
        molecule_id = tsv_path.name.replace("_CompileResults.tsv", "")
        figure_dir = output_dir / f"{molecule_id}_figures"
        metabolites = _parse_tsv(tsv_path, cache_path=output_dir / ".iupac_cache.json")
        result_sets.append(
            ResultSet(
                id=molecule_id,
                label=molecule_id,
                tsv_name=tsv_path.name,
                figure_dir=str(figure_dir),
                metabolite_count=len(metabolites),
                metabolites=metabolites,
                parent=load_parent_structure(output_dir, molecule_id),
            )
        )

    return {
        "available": bool(result_sets),
        "output_dir": str(output_dir),
        "result_sets": [
            {
                **{key: value for key, value in asdict(result_set).items() if key not in {"metabolites", "parent"}},
                "parent": parent_to_dict(result_set.parent),
                "metabolites": [metabolite_to_dict(item) for item in result_set.metabolites],
            }
            for result_set in result_sets
        ],
    }


def resolve_result_image(output_dir: Path, molecule_id: str, image_name: str) -> Optional[Path]:
    if not image_name or "/" in image_name or "\\" in image_name or ".." in image_name:
        return None
    if not re.fullmatch(r"(Molecule_\d+|Input)\.png", image_name):
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
