"""MetaTox Flask web application with Tailwind CSS and Flowbite."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request, send_file

from pipeline import (
    PipelineOptions,
    check_environment,
    get_work_dir,
    run_pipeline,
    sanitize_filename,
    summarize_outputs,
    zip_output_directory,
)


BIOTRANS_OPTIONS = {
    "allHuman": "All human biotransformations",
    "ecbased": "EC-based metabolism",
    "cyp450": "CYP450 metabolism",
    "phaseII": "Phase II conjugation",
    "hgut": "Human gut microbial",
    "superbio": "Superbio ordered steps",
    "envimicro": "Environmental microbial",
}

GLORYX_OPTIONS = {
    "phase_1_and_2": "Phase 1 and phase 2",
    "phase_1": "Phase 1 only",
    "phase_2": "Phase 2 only",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

_job_lock = threading.Lock()
_cancel_event = threading.Event()
_job_state: Dict[str, Any] = {
    "running": False,
    "logs": [],
    "output_dir": None,
    "zip_name": None,
    "summary": None,
    "error": None,
}


def _reset_job_state() -> None:
    _job_state["running"] = False
    _job_state["logs"] = []
    _job_state["output_dir"] = None
    _job_state["zip_name"] = None
    _job_state["summary"] = None
    _job_state["error"] = None


def _append_log(message: str) -> None:
    with _job_lock:
        _job_state["logs"].append(message)


def _environment_payload() -> Dict[str, Any]:
    status = check_environment()
    return {
        "singularity_available": status.singularity_available,
        "metatox_script_found": status.metatox_script_found,
        "work_dir": str(status.work_dir),
        "issues": status.issues,
        "notes": status.notes,
        "ready": not status.issues,
    }


def _resolve_input_path(form) -> Path:
    use_example = form.get("use_example") == "true"
    example_file = get_work_dir() / "ExempleInput.txt"

    if "input_file" in request.files:
        upload = request.files["input_file"]
        if upload and upload.filename:
            input_dir = get_work_dir() / "data" / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            destination = input_dir / sanitize_filename(upload.filename)
            upload.save(destination)
            return destination

    if use_example and example_file.is_file():
        return example_file

    raise ValueError("Upload an input file or enable the bundled example.")


def _build_options(form, input_path: Path) -> PipelineOptions:
    return PipelineOptions(
        input_file=input_path,
        outdir=(form.get("outdir") or "Results_Prediction").strip(),
        biotrans_type=form.get("biotrans_type") or "allHuman",
        nstep=int(form.get("nstep") or 1),
        cmode=int(form.get("cmode") or 3),
        phase1=int(form.get("phase1") or 1),
        phase2=int(form.get("phase2") or 1),
        phase_gloryx=form.get("phase_gloryx") or "phase_1_and_2",
        predictor_activate=form.get("predictor_activate") == "true",
        keep_tmp=form.get("keep_tmp") == "true",
    )


def _run_job(options: PipelineOptions) -> None:
    try:
        output_dir = run_pipeline(
            options,
            log_callback=_append_log,
            cancel_event=_cancel_event,
        )
        zip_path = output_dir.parent / f"{output_dir.name}.zip"
        zip_output_directory(output_dir, zip_path)
        with _job_lock:
            _job_state["output_dir"] = str(output_dir)
            _job_state["zip_name"] = zip_path.name
            _job_state["summary"] = summarize_outputs(output_dir)
    except Exception as exc:  # noqa: BLE001
        _append_log("")
        _append_log(f"ERROR: {exc}")
        with _job_lock:
            _job_state["error"] = str(exc)
    finally:
        with _job_lock:
            _job_state["running"] = False


@app.get("/")
def index():
    env = _environment_payload()
    example_available = (get_work_dir() / "ExempleInput.txt").is_file()
    return render_template(
        "index.html",
        biotrans_options=BIOTRANS_OPTIONS,
        gloryx_options=GLORYX_OPTIONS,
        env_status=env,
        example_available=example_available,
    )


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/environment")
def environment():
    return jsonify(_environment_payload())


@app.get("/api/job")
def job_status():
    with _job_lock:
        return jsonify(
            {
                "running": _job_state["running"],
                "logs": list(_job_state["logs"]),
                "output_dir": _job_state["output_dir"],
                "zip_name": _job_state["zip_name"],
                "summary": _job_state["summary"],
                "error": _job_state["error"],
            }
        )


@app.post("/api/run")
def start_run():
    with _job_lock:
        if _job_state["running"]:
            return jsonify({"error": "A prediction is already running."}), 409

    env = check_environment()
    if env.issues:
        return jsonify({"error": "\n".join(env.issues)}), 400

    try:
        input_path = _resolve_input_path(request.form)
        options = _build_options(request.form, input_path)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400

    _cancel_event.clear()
    with _job_lock:
        _reset_job_state()
        _job_state["running"] = True

    worker = threading.Thread(target=_run_job, args=(options,), daemon=True)
    worker.start()
    return jsonify({"status": "started"})


@app.post("/api/cancel")
def cancel_run():
    if not _job_state["running"]:
        return jsonify({"status": "idle"})
    _cancel_event.set()
    return jsonify({"status": "cancelling"})


@app.get("/api/download")
def download_results():
    zip_name = _job_state.get("zip_name")
    output_dir = _job_state.get("output_dir")
    if not zip_name or not output_dir:
        return jsonify({"error": "No results available yet."}), 404

    zip_path = Path(output_dir).parent / zip_name
    if not zip_path.is_file():
        return jsonify({"error": "Results archive not found."}), 404

    return send_file(zip_path, as_attachment=True, download_name=zip_name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501, debug=True)
