"""Tests for IUPAC name resolution helpers."""

from chemistry_utils import UNAVAILABLE_NAME, is_missing_iupac, smiles_to_iupac


def test_is_missing_iupac():
    assert is_missing_iupac("") is True
    assert is_missing_iupac("Name unavailable") is True
    assert is_missing_iupac("ethanol") is False


def test_smiles_to_iupac_known_compound():
    assert smiles_to_iupac("CCO") == "ethanol"


def test_smiles_to_iupac_complex_metabolite():
    smiles = "CC(C)C[C@H](C(=O)=NCC(=O)O)c1cc(-c2ccc(C(F)(F)F)cc2)cc(-c2ccc(C(F)(F)F)cc2)c1"
    name = smiles_to_iupac(smiles)
    assert name != UNAVAILABLE_NAME
    assert "trifluoromethyl" in name.lower()
