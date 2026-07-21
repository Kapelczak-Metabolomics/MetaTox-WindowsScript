#!/usr/bin/env python3
"""Background worker that runs MetaTox predictions outside the Gunicorn process."""

from __future__ import annotations

import os
import sys
import time

from elmaven_export import ELMAVEN_FILENAME, export_elmaven_knowns
from job_store import JobCancelMonitor, JobStore
from pipeline import run_pipeline, summarize_outputs, zip_output_directory
from results_viewer import ensure_parent_structures


def _configure_runtime() -> None:
    os.environ.setdefault("METATOX_VERBOSE", "true")
    os.environ.setdefault("METATOX_NATIVE_COMPILE", "true")
    os.environ.pop("APPTAINER_BINDPATH", None)
    os.environ.pop("SINGULARITY_BINDPATH", None)
    os.environ.setdefault("APPTAINER_NO_MOUNT", "cwd,home,tmp,/etc/localtime")
    os.environ.setdefault("SINGULARITY_NO_MOUNT", "cwd,home,tmp,/etc/localtime")
    os.environ.setdefault("APPTAINER_TMPDIR", "/tmp/apptainer")
    os.environ.setdefault("SINGULARITY_TMPDIR", "/tmp/apptainer")
    os.makedirs("/tmp/apptainer", exist_ok=True)


def run_once(store: JobStore) -> bool:
    options = store.claim_request()
    if options is None:
        return False

    cancel_event = JobCancelMonitor(store)
    cancel_event.clear()
    store.update_state(
        running=True,
        error=None,
        output_dir=None,
        zip_path=None,
        zip_ready=False,
        zip_name=None,
        summary=None,
    )

    def log_callback(message: str) -> None:
        store.append_log(message)

    try:
        output_dir = run_pipeline(
            options,
            log_callback=log_callback,
            cancel_event=cancel_event,
        )
        ensure_parent_structures(output_dir, options.input_file)
        if options.export_elmaven:
            elmaven_path = export_elmaven_knowns(output_dir)
            store.append_log(f"El-MAVEN knowns list: {elmaven_path}")
        zip_path = zip_output_directory(output_dir)
        store.update_state(
            running=False,
            output_dir=str(output_dir),
            zip_path=str(zip_path),
            zip_ready=zip_path.is_file() and zip_path.stat().st_size > 0,
            zip_name=zip_path.name,
            summary=summarize_outputs(output_dir),
            error=None,
        )
        store.append_log(f"Results archive: {zip_path} ({zip_path.stat().st_size} bytes)")
    except Exception as exc:  # noqa: BLE001
        store.append_log("")
        store.append_log(f"ERROR: {exc}")
        store.update_state(running=False, error=str(exc))
    finally:
        cancel_event.clear()

    return True


def main() -> int:
    _configure_runtime()
    store = JobStore()
    print("MetaTox job worker started.", flush=True)

    while True:
        try:
            if not run_once(store):
                time.sleep(0.5)
        except Exception as exc:  # noqa: BLE001
            print(f"Job worker error: {exc}", file=sys.stderr, flush=True)
            store.update_state(running=False, error=str(exc))
            time.sleep(1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
