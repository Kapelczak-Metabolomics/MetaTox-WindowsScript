"""Tests for BioTransformer runtime helper."""

from pathlib import Path
from unittest.mock import patch

import prepare_biotransformer_runtime as helper


def test_runtime_complete_requires_supportfiles_and_config(tmp_path: Path):
    runtime = tmp_path / "bt"
    runtime.mkdir()
    (runtime / "BioTransformer.jar").write_bytes(b"jar")
    (runtime / "btkb").mkdir()
    assert helper.runtime_complete(runtime) is False

    (runtime / "supportfiles").mkdir()
    (runtime / "supportfiles" / "MVDModels").mkdir()
    (runtime / "config.json").write_text("{}", encoding="utf-8")
    assert helper.runtime_complete(runtime) is True


def test_run_prediction_writes_placeholder_when_csv_missing(tmp_path: Path):
    runtime = tmp_path / "bt"
    runtime.mkdir()
    (runtime / "BioTransformer.jar").write_bytes(b"jar")
    (runtime / "btkb").mkdir()
    (runtime / "supportfiles").mkdir()
    (runtime / "supportfiles" / "MVDModels").mkdir()
    (runtime / "config.json").write_text("{}", encoding="utf-8")
    (runtime / helper.READY_MARKER).write_text("ok\n", encoding="utf-8")

    output = tmp_path / "out" / "result.csv"

    with patch.object(helper, "find_singularity", return_value="/bin/true"), patch.object(
        helper.subprocess, "run", return_value=type("R", (), {"returncode": 0})()
    ):
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
