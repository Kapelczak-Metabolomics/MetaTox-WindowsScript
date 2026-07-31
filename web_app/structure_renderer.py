"""Render molecule structures for the results viewer."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

PARENT_IMAGE_NAME = "Input.png"
PARENT_META_NAME = "parent.json"


def render_smiles_to_png(smiles: str, destination: Path, size: Tuple[int, int] = (320, 320)) -> bool:
    cleaned = (smiles or "").strip()
    if not cleaned:
        return False

    try:
        from rdkit import Chem
        from rdkit.Chem import Draw
    except ImportError:
        return False

    molecule = Chem.MolFromSmiles(cleaned)
    if molecule is None:
        return False

    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    Draw.MolToFile(molecule, str(destination), size=size)
    return destination.is_file() and destination.stat().st_size > 0


def smiles_formula_and_mass(smiles: str) -> Tuple[str, str]:
    cleaned = (smiles or "").strip()
    if not cleaned:
        return "", ""

    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors
    except ImportError:
        return "", ""

    molecule = Chem.MolFromSmiles(cleaned)
    if molecule is None:
        return "", ""

    formula = rdMolDescriptors.CalcMolFormula(molecule)
    try:
        from molmass import Formula

        mass_value = Formula(formula).monoisotopic_mass + 1.007825
    except Exception:
        mass_value = Descriptors.ExactMolWt(molecule) + 1.007825

    return formula, f"{mass_value:.4f}"
