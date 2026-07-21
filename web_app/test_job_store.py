"""Tests for file-backed job state."""

from pathlib import Path

import pytest

from job_store import JobClearError, JobStore, options_from_dict, options_to_dict
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


def test_clear_session_resets_state_and_deletes_output(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    store = JobStore()
    output_dir = tmp_path / "data" / "output" / "Results_Prediction"
    output_dir.mkdir(parents=True)
    (output_dir / "Drug_CompileResults.tsv").write_text("test\n", encoding="utf-8")
    zip_path = output_dir / "MetaTox_results.zip"
    zip_path.write_text("zip", encoding="utf-8")

    store.update_state(
        running=False,
        output_dir=str(output_dir),
        zip_path=str(zip_path),
        zip_ready=True,
        zip_name=zip_path.name,
        summary="Done",
    )
    store.append_log("Finished")

    cleared = store.clear_session()
    assert cleared.running is False
    assert cleared.output_dir is None
    assert store.read_logs() == []
    assert not output_dir.exists()


def test_clear_session_rejects_running_job(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    store = JobStore()
    store.update_state(running=True)

    with pytest.raises(JobClearError, match="running"):
        store.clear_session()
