"""Tests for the GLORYx local/API helper."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "Scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import gloryx_api  # noqa: E402
import gloryx_local  # noqa: E402


def test_write_empty_csv(tmp_path: Path):
    output = tmp_path / "gloryx.csv"
    gloryx_api.write_empty_csv(str(output))
    assert output.read_text(encoding="utf-8").splitlines() == [
        "metabolite_smiles,score,pathway",
    ]


def test_result_row_maps_nerdd_fields():
    row = gloryx_api._result_row(
        {
            "metabolite_smiles": "CCO",
            "priority_score": 0.9,
            "reaction_type": "hydroxylation",
            "derivative_id": 1,
        }
    )
    assert row == ["CCO", "0.9", "hydroxylation"]


def test_local_predicts_ethanol_metabolites():
    rows = gloryx_local.predict_metabolites("CCO", "phase_1_and_2")
    assert len(rows) >= 1
    assert all("." not in smi for smi, _score, _path in rows)


def test_run_gloryx_defaults_to_local(tmp_path: Path):
    output = tmp_path / "gloryx.csv"
    with patch.object(gloryx_local, "run_gloryx_local", return_value=0) as local_run, patch.object(
        gloryx_api, "run_gloryx_api"
    ) as api_run:
        assert gloryx_api.run_gloryx("CCO", "phase_1_and_2", str(output), backend="local") == 0
        local_run.assert_called_once()
        api_run.assert_not_called()


def test_run_gloryx_api_backend(tmp_path: Path):
    output = tmp_path / "gloryx.csv"
    with patch.object(gloryx_api, "run_gloryx_api", return_value=0) as api_run:
        assert gloryx_api.run_gloryx("CCO", "phase_1_and_2", str(output), backend="api") == 0
        api_run.assert_called_once()


def test_main_cli_fails_hard_on_error_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output = tmp_path / "gloryx.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gloryx_api.py",
            "--backend",
            "local",
            "--phase",
            "phase_1_and_2",
            "--smile",
            "CCO",
            "--output",
            str(output),
        ],
    )

    with patch.object(
        gloryx_api,
        "run_gloryx",
        side_effect=gloryx_api.GloryxApiError("service unavailable"),
    ):
        assert gloryx_api.main() == 1

    assert output.read_text(encoding="utf-8").startswith("metabolite_smiles,score,pathway")


def test_is_submit_throttle_detects_nerdd_message():
    assert gloryx_api._is_submit_throttle(
        gloryx_api.GloryxApiError(
            'GLORYx HTTP 429: {"detail":"The server is initializing a job you submitted recently."}'
        )
    )
