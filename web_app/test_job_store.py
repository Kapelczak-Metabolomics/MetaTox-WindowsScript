"""Tests for file-backed job state."""

from pathlib import Path

from job_store import JobStore, options_from_dict, options_to_dict
from pipeline import PipelineOptions


def test_job_store_round_trip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    store = JobStore()

    options = PipelineOptions(
        input_file=tmp_path / "input.txt",
        outdir="data/output/Results_Prediction",
        biotrans_type="allHuman",
    )
    (tmp_path / "input.txt").write_text("Nicotine,CN1CCC[C@H]1c2cccnc2\n", encoding="utf-8")

    store.reset_for_run()
    store.submit_request(options)

    claimed = store.claim_request()
    assert claimed is not None
    assert claimed.biotrans_type == "allHuman"
    assert claimed.input_file.name == "input.txt"


def test_options_serialization(tmp_path: Path):
    options = PipelineOptions(
        input_file=tmp_path / "input.txt",
        outdir="data/output/Results_Prediction",
    )
    restored = options_from_dict(options_to_dict(options))
    assert restored.outdir == options.outdir
    assert str(restored.input_file) == str(options.input_file)
