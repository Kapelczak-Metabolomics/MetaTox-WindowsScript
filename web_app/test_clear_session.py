"""Tests for clearing a finished prediction session."""

from pathlib import Path

import app as app_module
from app import app, get_job_store


def _reset_job_store() -> None:
    app_module._job_store = None


def test_clear_session_endpoint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    _reset_job_store()
    client = app.test_client()

    output_dir = tmp_path / "data" / "output" / "Results_Prediction"
    output_dir.mkdir(parents=True)
    (output_dir / "Drug_CompileResults.tsv").write_text("test\n", encoding="utf-8")

    store = get_job_store()
    store.update_state(
        running=False,
        output_dir=str(output_dir),
        zip_ready=True,
        summary="Done",
    )
    store.append_log("Finished")

    response = client.post("/api/clear")
    assert response.status_code == 200
    assert response.get_json()["status"] == "cleared"
    assert store.read_state().output_dir is None
    assert store.read_logs() == []
    assert not output_dir.exists()


def test_clear_session_rejects_running_prediction(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    _reset_job_store()
    client = app.test_client()

    store = get_job_store()
    store.update_state(running=True)

    response = client.post("/api/clear")
    assert response.status_code == 409
    assert "running" in response.get_json()["error"].lower()
