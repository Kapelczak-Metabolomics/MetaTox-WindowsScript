"""Chemistry helpers shared by compilation and the web viewer."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional

UNAVAILABLE_NAME = "Name unavailable"
PUBCHEM_IUPAC_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/property/IUPACName/TXT"


def canonicalize_smiles(smiles: str) -> str:
    try:
        from rdkit import Chem

        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            return smiles
        return Chem.MolToSmiles(molecule, isomericSmiles=True)
    except Exception:
        return smiles


def _smiles_via_inchi(smiles: str) -> str:
    """Normalize difficult SMILES through an InChI round-trip."""
    try:
        from openbabel import pybel
        from rdkit import Chem
    except ImportError:
        return ""

    try:
        inchi = pybel.readstring("smi", smiles).write("inchi").strip()
        if not inchi.startswith("InChI="):
            return ""
        molecule = Chem.MolFromInchi(inchi)
        if molecule is None:
            return ""
        return Chem.MolToSmiles(molecule, isomericSmiles=True)
    except Exception:
        return ""


def _openclatura_iupac(smiles: str) -> str:
    try:
        from openclatura import name_smiles
        from rdkit import Chem
    except ImportError:
        return ""

    normalized_candidates: List[str] = []
    for candidate in {smiles, canonicalize_smiles(smiles)}:
        if not candidate:
            continue
        molecule = Chem.MolFromSmiles(candidate)
        if molecule is None:
            continue
        normalized_candidates.append(Chem.MolToSmiles(molecule, isomericSmiles=True))

    via_inchi = _smiles_via_inchi(smiles)
    if via_inchi:
        normalized_candidates.append(via_inchi)

    for candidate in dict.fromkeys(normalized_candidates):
        try:
            name = (name_smiles(candidate) or "").strip()
            if name:
                return name
        except Exception:
            continue

    return ""


def _pubchem_iupac(smiles: str, timeout: int = 20) -> str:
    data = urllib.parse.urlencode({"smiles": smiles}).encode("utf-8")
    request = urllib.request.Request(
        PUBCHEM_IUPAC_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            name = response.read().decode("utf-8", errors="replace").strip()
            if name and "html" not in name.lower():
                return name
    except urllib.error.HTTPError:
        return ""
    except (urllib.error.URLError, TimeoutError, ValueError):
        return ""
    return ""


def smiles_to_iupac(smiles: str, timeout: int = 20) -> str:
    """Resolve an IUPAC name for a SMILES string."""
    cleaned = (smiles or "").strip()
    if not cleaned or cleaned.upper() == "NA":
        return ""

    candidates: List[str] = []
    seen = set()
    for candidate in (cleaned, canonicalize_smiles(cleaned), _smiles_via_inchi(cleaned)):
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    for candidate in candidates:
        name = _pubchem_iupac(candidate, timeout=timeout)
        if name:
            return name

    for candidate in candidates:
        name = _openclatura_iupac(candidate)
        if name:
            return name

    return UNAVAILABLE_NAME


def load_iupac_cache(cache_path: Path) -> Dict[str, str]:
    if not cache_path.is_file():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return {str(key): str(value) for key, value in payload.items()}
    return {}


def save_iupac_cache(cache_path: Path, cache: Dict[str, str]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def resolve_iupac_batch(
    smiles_list: Iterable[str],
    cache_path: Optional[Path] = None,
    timeout: int = 20,
) -> Dict[str, str]:
    """Resolve IUPAC names for many SMILES strings with optional disk cache."""
    unique_smiles: List[str] = []
    seen = set()
    for smiles in smiles_list:
        cleaned = (smiles or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique_smiles.append(cleaned)

    cache = load_iupac_cache(cache_path) if cache_path else {}
    resolved: Dict[str, str] = {}

    for smiles in unique_smiles:
        cached = cache.get(smiles)
        if cached and not is_missing_iupac(cached):
            resolved[smiles] = cached
            continue

        name = smiles_to_iupac(smiles, timeout=timeout)
        resolved[smiles] = name
        cache[smiles] = name

    if cache_path:
        save_iupac_cache(cache_path, cache)

    return resolved


def is_missing_iupac(value: Optional[str]) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized in {"", "na", "name unavailable", "n/a"}
