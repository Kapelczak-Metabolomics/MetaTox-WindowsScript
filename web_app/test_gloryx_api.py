"""Tests for the GLORYx API helper."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "Scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import gloryx_api  # noqa: E402


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


def test_result_row_skips_parent_rows():
    assert (
        gloryx_api._result_row(
            {
                "metabolite_smiles": "CCO",
                "derivative_id": 0,
                "priority_score": "",
                "reaction_type": "",
            }
        )
        is None
    )


def test_extract_job_id_supports_nested_payload():
    assert gloryx_api._extract_job_id({"job": {"id": "abc123"}}) == "abc123"


def test_run_gloryx_writes_results(tmp_path: Path):
    output = tmp_path / "gloryx.csv"
    responses = [
        {"id": "job-1"},
        {"status": "completed"},
        {
            "data": [
                {
                    "metabolite_smiles": "CCO",
                    "priority_score": 1.0,
                    "reaction_type": "oxidation",
                    "derivative_id": 1,
                }
            ]
        },
    ]

    with patch.object(gloryx_api, "_request_json", side_effect=responses), patch.object(
        gloryx_api, "_queue_info", return_value=None
    ), patch.object(gloryx_api, "_fetch_output_csv_rows", return_value=[]):
        assert gloryx_api.run_gloryx("CCO", "phase_1_and_2", str(output)) == 0

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "metabolite_smiles,score,pathway"
    assert "CCO" in lines[1]


def test_main_cli_fails_hard_on_api_error_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output = tmp_path / "gloryx.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        ["gloryx_api.py", "--phase", "phase_1_and_2", "--smile", "CCO", "--output", str(output)],
    )

    with patch.object(
        gloryx_api,
        "run_gloryx",
        side_effect=gloryx_api.GloryxApiError("service unavailable"),
    ):
        assert gloryx_api.main() == 1

    assert output.read_text(encoding="utf-8").startswith("metabolite_smiles,score,pathway")


def test_main_cli_soft_fail_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output = tmp_path / "gloryx.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gloryx_api.py",
            "--phase",
            "phase_1_and_2",
            "--smile",
            "CCO",
            "--output",
            str(output),
            "--soft-fail",
        ],
    )

    with patch.object(
        gloryx_api,
        "run_gloryx",
        side_effect=gloryx_api.GloryxApiError("service unavailable"),
    ):
        assert gloryx_api.main() == 0
