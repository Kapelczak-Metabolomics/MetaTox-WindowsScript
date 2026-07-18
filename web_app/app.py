"""MetaTox Flask web application with Tailwind CSS and Flowbite."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

from job_store import JobStore
from pipeline import (
    PipelineOptions,
    check_environment,
    extract_results_zip,
    get_work_dir,
    metapredictor_is_available,
    sanitize_filename,
    validate_input_file,
    zip_output_directory,
)
from elmaven_export import elmaven_knowns_path, export_elmaven_knowns
from results_viewer import load_results_for_viewer, resolve_iupac_for_smiles, resolve_result_image


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
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024
_job_store: JobStore | None = None


def get_job_store() -> JobStore:
    global _job_store
    if _job_store is None:
        _job_store = JobStore()
    return _job_store


def _environment_payload():
    status = check_environment()
    return {
        "singularity_available": status.singularity_available,
        "metatox_script_found": status.metatox_script_found,
        "metapredictor_available": status.metapredictor_available,
        "work_dir": str(status.work_dir),
        "issues": status.issues,
        "notes": status.notes,
        "ready": not status.issues,
    }


def _save_pasted_input(text: str) -> Path:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Paste at least one molecule line or upload a file.")

    input_dir = get_work_dir() / "data" / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    destination = input_dir / "pasted_input.txt"
    destination.write_text(cleaned + "\n", encoding="utf-8")
    validate_input_file(destination)
    return destination


def _resolve_input_path(form) -> Path:
    use_example = form.get("use_example") == "true"
    example_file = get_work_dir() / "ExempleInput.txt"
    pasted_text = (form.get("input_text") or "").strip()

    if "input_file" in request.files:
        upload = request.files["input_file"]
        if upload and upload.filename:
            input_dir = get_work_dir() / "data" / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            destination = input_dir / sanitize_filename(upload.filename)
            upload.save(destination)
            return destination

    if pasted_text:
        return _save_pasted_input(pasted_text)

    if use_example and example_file.is_file():
        return example_file

    raise ValueError("Upload a file, paste molecule lines directly, or enable the bundled example.")


def _build_options(form, input_path: Path) -> PipelineOptions:
    return PipelineOptions(
        input_file=input_path,
        outdir=(form.get("outdir") or "data/output/Results_Prediction").strip(),
        biotrans_type=form.get("biotrans_type") or "allHuman",
        nstep=int(form.get("nstep") or 1),
        cmode=int(form.get("cmode") or 3),
        phase1=int(form.get("phase1") or 1),
        phase2=int(form.get("phase2") or 1),
        phase_gloryx=form.get("phase_gloryx") or "phase_1_and_2",
        predictor_activate=form.get("predictor_activate") == "true",
        keep_tmp=form.get("keep_tmp") == "true",
        export_elmaven=form.get("export_elmaven") == "true",
    )


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
    return jsonify(get_job_store().snapshot_for_api())


@app.post("/api/run")
def start_run():
    snapshot = get_job_store().read_state()
    if snapshot.running or get_job_store().request_path.is_file():
        return jsonify({"error": "A prediction is already running."}), 409

    env = check_environment()
    if env.issues:
        return jsonify({"error": "\n".join(env.issues)}), 400

    try:
        input_path = _resolve_input_path(request.form)
        options = _build_options(request.form, input_path)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400

    if options.predictor_activate and not metapredictor_is_available():
        return jsonify(
            {
                "error": (
                    "Meta-Predictor is not installed in this container. "
                    "Disable Meta-Predictor or follow docker/README.md to add it."
                )
            }
        ), 400

    get_job_store().reset_for_run()
    get_job_store().submit_request(options)
    return jsonify({"status": "started"})


@app.post("/api/cancel")
def cancel_run():
    snapshot = get_job_store().read_state()
    if not snapshot.running:
        return jsonify({"status": "idle"})
    get_job_store().request_cancel()
    return jsonify({"status": "cancelling"})


@app.get("/api/download")
def download_results():
    snapshot = get_job_store().read_state()

    if snapshot.zip_path:
        zip_path = Path(snapshot.zip_path)
        if zip_path.is_file() and zip_path.stat().st_size > 0:
            return send_file(
                zip_path,
                as_attachment=True,
                download_name=zip_path.name,
                mimetype="application/zip",
            )

    if snapshot.output_dir:
        output_dir = Path(snapshot.output_dir)
        if output_dir.is_dir() and list(output_dir.glob("*_CompileResults.tsv")):
            zip_path = zip_output_directory(output_dir)
            get_job_store().update_state(
                zip_path=str(zip_path),
                zip_ready=True,
                zip_name=zip_path.name,
            )
            return send_file(
                zip_path,
                as_attachment=True,
                download_name=zip_path.name,
                mimetype="application/zip",
            )

    return jsonify({"error": "No results archive is available yet."}), 404


def _output_dir_from_request() -> Path | None:
    output_dir = request.args.get("output_dir")
    if output_dir:
        candidate = Path(output_dir).resolve()
        allowed_root = (get_work_dir() / "data" / "output").resolve()
        if allowed_root in candidate.parents or candidate == allowed_root:
            return candidate

    snapshot = get_job_store().read_state()
    if snapshot.output_dir:
        return Path(snapshot.output_dir)
    return None


@app.post("/api/results/upload-zip")
def upload_results_zip():
    upload = request.files.get("results_zip")
    if not upload or not upload.filename:
        return jsonify({"error": "Choose a MetaTox results .zip file to upload."}), 400

    filename = sanitize_filename(upload.filename)
    if not filename.lower().endswith(".zip"):
        return jsonify({"error": "Only .zip archives are supported."}), 400

    upload_root = (get_work_dir() / "data" / "output" / "viewer_uploads").resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    destination = upload_root / f"{Path(filename).stem}_{uuid.uuid4().hex[:8]}"
    archive_path = upload_root / f"upload_{uuid.uuid4().hex[:8]}.zip"

    try:
        upload.save(archive_path)
        output_dir = extract_results_zip(archive_path, destination)
    except Exception as exc:  # noqa: BLE001
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        return jsonify({"error": str(exc)}), 400
    finally:
        archive_path.unlink(missing_ok=True)

    return jsonify(
        {
            "output_dir": str(output_dir),
            "label": filename,
            "source": "upload",
        }
    )


@app.get("/api/results/viewer")
def results_viewer_api():
    output_dir = _output_dir_from_request()
    if not output_dir:
        return jsonify({"available": False, "result_sets": []})
    return jsonify(load_results_for_viewer(output_dir))


@app.post("/api/results/iupac")
def results_iupac_api():
    output_dir = _output_dir_from_request()
    if not output_dir:
        return jsonify({"error": "No output directory is available."}), 404

    payload = request.get_json(silent=True) or {}
    smiles_list = payload.get("smiles") or []
    if not isinstance(smiles_list, list):
        return jsonify({"error": "Expected a JSON array field named 'smiles'."}), 400

    cleaned = [str(item).strip() for item in smiles_list if str(item).strip()]
    if not cleaned:
        return jsonify({"names": {}})

    names = resolve_iupac_for_smiles(output_dir, cleaned)
    return jsonify({"names": names})


@app.get("/api/results/elmaven")
def download_elmaven_knowns():
    output_dir = _output_dir_from_request()
    if not output_dir:
        return jsonify({"error": "No output directory is available."}), 404

    elmaven_path = elmaven_knowns_path(output_dir)
    if not elmaven_path.is_file():
        try:
            elmaven_path = export_elmaven_knowns(output_dir)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 404

    return send_file(
        elmaven_path,
        as_attachment=True,
        download_name=elmaven_path.name,
        mimetype="text/csv",
    )


@app.get("/api/results/image/<molecule_id>/<path:image_name>")
def results_image(molecule_id: str, image_name: str):
    output_dir = _output_dir_from_request()
    if not output_dir:
        abort(404)
    image_path = resolve_result_image(output_dir, molecule_id, image_name)
    if not image_path:
        abort(404)
    return send_file(image_path, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501, debug=True)
