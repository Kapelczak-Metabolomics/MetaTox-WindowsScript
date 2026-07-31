#!/usr/bin/env python3
"""Offline GLORYx-style metabolite prediction using published reaction rules.

Uses the GLORYx/GLORYxR SMIRKS rule set with RDKit. This avoids the public NERDD
API (which rate-limits and queues unpredictably). Ranking uses the published
priority levels (common=1.0, uncommon=0.2) when FAME3 models are unavailable.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

RULES_DIR = Path(__file__).resolve().parent / "gloryx_rules"
DEFAULT_RULES = RULES_DIR / "gloryx_reactionrules_connect.csv"
PHASE_CHOICES = ("phase_1", "phase_2", "phase_1_and_2")


class GloryxLocalError(RuntimeError):
    pass


def _require_rdkit():
    try:
        from rdkit import Chem  # noqa: F401
        from rdkit.Chem import AllChem  # noqa: F401
        from rdkit.rdBase import BlockLogs  # noqa: F401
    except ImportError as exc:
        raise GloryxLocalError(
            "RDKit is required for offline GLORYx. "
            "Install it in the MetaTox image (requirements-companion.txt)."
        ) from exc


def _phase_matches(subset: str, phase: str) -> bool:
    subset_l = subset.lower()
    if phase == "phase_1":
        return "phase 1" in subset_l
    if phase == "phase_2":
        return "phase 2" in subset_l
    return "phase 1" in subset_l or "phase 2" in subset_l


def _priority_score(priority: str) -> float:
    return 1.0 if str(priority).strip().lower() == "common" else 0.2


def load_rules(rules_path: Path, phase: str) -> List[Dict[str, str]]:
    if not rules_path.is_file():
        raise GloryxLocalError(f"GLORYx rules file not found: {rules_path}")
    with rules_path.open(encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("SMIRKS") and _phase_matches(row.get("Name of rule subset", ""), phase)
        ]
    if not rows:
        raise GloryxLocalError(f"No GLORYx rules matched phase={phase} in {rules_path}")
    return rows


def _product_mols(product) -> Iterable:
    from rdkit import Chem
    from rdkit.rdBase import BlockLogs

    with BlockLogs():
        try:
            Chem.SanitizeMol(product)
        except Exception:
            return []
        try:
            product = Chem.RemoveHs(product)
        except Exception:
            return []

        frags = Chem.GetMolFrags(product, asMols=True, sanitizeFrags=False)
        kept = []
        for frag in frags:
            try:
                Chem.SanitizeMol(frag)
            except Exception:
                continue
            # Same heavy-atom floor as GLORYx/GLORYxR.
            if frag.GetNumHeavyAtoms() < 3:
                continue
            kept.append(frag)
    return kept


def predict_metabolites(
    smiles: str,
    phase: str,
    *,
    rules_path: Optional[Path] = None,
) -> List[Tuple[str, float, str]]:
    _require_rdkit()
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.rdBase import BlockLogs

    if phase not in PHASE_CHOICES:
        raise GloryxLocalError(f"Unsupported phase: {phase}")

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise GloryxLocalError(f"Could not parse SMILES: {smiles}")

    mol_h = Chem.AddHs(mol)
    rules = load_rules(Path(rules_path or DEFAULT_RULES), phase)
    best: Dict[str, Tuple[float, str]] = {}

    for row in rules:
        try:
            reaction = AllChem.ReactionFromSmarts(row["SMIRKS"])
        except Exception:
            continue
        if reaction is None:
            continue

        with BlockLogs():
            try:
                product_sets = reaction.RunReactants((mol_h,))
            except Exception:
                continue

        score = _priority_score(row.get("Priority level", ""))
        pathway = row.get("Reaction name") or row.get("Name of rule subset") or "unknown"
        for product_set in product_sets:
            for product in product_set:
                for frag in _product_mols(product):
                    out = Chem.MolToSmiles(frag)
                    if not out:
                        continue
                    previous = best.get(out)
                    if previous is None or score > previous[0]:
                        best[out] = (score, pathway)

    rows = [(smi, score, pathway) for smi, (score, pathway) in best.items()]
    rows.sort(key=lambda item: (-item[1], item[2], item[0]))
    return rows


def write_csv(path: Path, rows: Sequence[Sequence[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metabolite_smiles", "score", "pathway"])
        writer.writerows(rows)


def run_gloryx_local(smiles: str, phase: str, output_path: str, rules_path: Optional[str] = None) -> int:
    rows = predict_metabolites(smiles, phase, rules_path=Path(rules_path) if rules_path else None)
    write_csv(Path(output_path), [(smi, f"{score:g}", pathway) for smi, score, pathway in rows])
    print(
        f"GLORYx local predicted {len(rows)} metabolite(s) for phase={phase} -> {output_path}",
        file=sys.stderr,
    )
    if not rows:
        raise GloryxLocalError(
            f"Offline GLORYx produced 0 metabolites for SMILES={smiles!r} phase={phase}"
        )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=PHASE_CHOICES)
    parser.add_argument("--smile", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    args = parser.parse_args(argv)
    try:
        return run_gloryx_local(args.smile.strip(), args.phase, args.output, args.rules)
    except GloryxLocalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        write_csv(Path(args.output), [])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
