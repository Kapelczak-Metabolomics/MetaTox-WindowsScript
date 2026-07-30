"""Tests for BioTransformer runtime helper."""

import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "Scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import prepare_biotransformer_runtime as helper  # noqa: E402


def test_runtime_complete_requires_supportfiles_and_config(tmp_path: Path):
    runtime = tmp_path / "bt"
    runtime.mkdir()
    (runtime / "BioTransformer.jar").write_bytes(b"jar")
    (runtime / "btkb").mkdir()
    assert helper.runtime_complete(runtime) is False

    (runtime / "btkb" / "enzymes.json").write_text("{}", encoding="utf-8")
    (runtime / "supportfiles").mkdir()
    (runtime / "supportfiles" / "MVDModels").mkdir()
    (runtime / "config.json").write_text("{}", encoding="utf-8")
    assert helper.runtime_complete(runtime) is True


def test_strip_smiles_stereochemistry():
    assert helper.strip_smiles_stereochemistry("Fc1ccc(cc1)[C@@]3(OCc2cc(C#N)ccc23)CCCN(C)C") == (
        "Fc1ccc(cc1)[C]3(OCc2cc(C#N)ccc23)CCCN(C)C"
    )
    assert helper.has_stereochemistry("C[C@H](O)C") is True
    assert helper.has_stereochemistry("CCO") is False


def test_run_prediction_retries_without_stereo(tmp_path: Path):
    runtime = tmp_path / "bt"
    runtime.mkdir()
    (runtime / "BioTransformer.jar").write_bytes(b"jar")
    (runtime / "btkb").mkdir()
    (runtime / "btkb" / "enzymes.json").write_text("{}", encoding="utf-8")
    (runtime / "supportfiles").mkdir()
    (runtime / "supportfiles" / "MVDModels").mkdir()
    (runtime / "config.json").write_text("{}", encoding="utf-8")
    (runtime / helper.READY_MARKER).write_text("ok\n", encoding="utf-8")

    output = tmp_path / "out" / "result.csv"
    calls = {"n": 0}

    def fake_run_once(**kwargs):
        calls["n"] += 1
        output.parent.mkdir(parents=True, exist_ok=True)
        if calls["n"] == 1:
            output.write_text("SMILES\n", encoding="utf-8")
        else:
            assert "@" not in kwargs["smiles"]
            output.write_text("SMILES\nCCO\n", encoding="utf-8")
        return 0

    with patch.object(helper, "find_java", return_value="/usr/bin/java"), patch.object(
        helper, "_run_once", side_effect=fake_run_once
    ):
        code = helper.run_prediction(
            bt_type="allHuman",
            cmode=3,
            nstep=1,
            smiles="Fc1ccc(cc1)[C@@]3(OCc2cc(C#N)ccc23)CCCN(C)C",
            output=output,
            runtime=runtime,
        )

    assert code == 0
    assert calls["n"] == 2
    assert helper.count_metabolite_rows(output) == 1


def test_run_prediction_writes_placeholder_when_csv_missing(tmp_path: Path):
    runtime = tmp_path / "bt"
    runtime.mkdir()
    (runtime / "BioTransformer.jar").write_bytes(b"jar")
    (runtime / "btkb").mkdir()
    (runtime / "btkb" / "enzymes.json").write_text("{}", encoding="utf-8")
    (runtime / "supportfiles").mkdir()
    (runtime / "supportfiles" / "MVDModels").mkdir()
    (runtime / "config.json").write_text("{}", encoding="utf-8")
    (runtime / helper.READY_MARKER).write_text("ok\n", encoding="utf-8")

    output = tmp_path / "out" / "result.csv"

    with patch.object(helper, "find_java", return_value=None), patch.object(
        helper, "find_singularity", return_value="/bin/true"
    ), patch.object(helper.subprocess, "run", return_value=type("R", (), {"returncode": 0})()):
        code = helper.run_prediction(
            bt_type="allHuman",
            cmode=3,
            nstep=1,
            smiles="CCO",
            output=output,
            runtime=runtime,
        )

    assert code == 0
    assert output.read_text(encoding="utf-8").startswith("SMILES")
