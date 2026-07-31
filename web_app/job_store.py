"""File-backed job state so predictions survive Gunicorn worker restarts."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pipeline import PipelineOptions, get_work_dir


class JobClearError(RuntimeError):
    """Raised when the current session cannot be cleared."""


@dataclass
class JobSnapshot:
    running: bool = False
    output_dir: Optional[str] = None
    zip_path: Optional[str] = None
    zip_ready: bool = False
    zip_name: Optional[str] = None
    summary: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "JobSnapshot":
        return cls(
            running=bool(payload.get("running", False)),
            output_dir=payload.get("output_dir"),
            zip_path=payload.get("zip_path"),
            zip_ready=bool(payload.get("zip_ready", False)),
            zip_name=payload.get("zip_name"),
            summary=payload.get("summary"),
            error=payload.get("error"),
        )


class JobStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        work_dir = root or (get_work_dir() / "data" / "job")
        self.root = work_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.log_path = self.root / "logs.txt"
        self.request_path = self.root / "request.json"
        self.cancel_path = self.root / "cancel"
        self._lock = threading.Lock()

    def _read_state_unlocked(self) -> JobSnapshot:
        if not self.state_path.is_file():
            return JobSnapshot()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return JobSnapshot()
        return JobSnapshot.from_dict(payload)

    def _write_state_unlocked(self, snapshot: JobSnapshot) -> None:
        temp_path = self.state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    def read_state(self) -> JobSnapshot:
        with self._lock:
            return self._read_state_unlocked()

    def update_state(self, **fields: Any) -> JobSnapshot:
        with self._lock:
            snapshot = self._read_state_unlocked()
            for key, value in fields.items():
                setattr(snapshot, key, value)
            self._write_state_unlocked(snapshot)
            return snapshot

    def reset_for_run(self) -> None:
        with self._lock:
            self.log_path.write_text("", encoding="utf-8")
            self.cancel_path.unlink(missing_ok=True)
            self.request_path.unlink(missing_ok=True)
            self._write_state_unlocked(JobSnapshot(running=True))

    def append_log(self, message: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")

    def read_logs(self) -> list[str]:
        if not self.log_path.is_file():
            return []
        text = self.log_path.read_text(encoding="utf-8")
        if not text:
            return []
        return text.splitlines()

    def submit_request(self, options: PipelineOptions) -> None:
        payload = {
            "submitted_at": time.time(),
            "options": options_to_dict(options),
        }
        temp_path = self.request_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.request_path)

    def claim_request(self) -> Optional[PipelineOptions]:
        with self._lock:
            if not self.request_path.is_file():
                return None
            try:
                payload = json.loads(self.request_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.request_path.unlink(missing_ok=True)
                return None
            self.request_path.unlink(missing_ok=True)

        options_payload = payload.get("options", {})
        if not options_payload.get("input_file"):
            return None
        return options_from_dict(options_payload)

    def wait_for_request(self, poll_seconds: float = 0.5) -> PipelineOptions:
        while True:
            options = self.claim_request()
            if options is not None:
                return options
            time.sleep(poll_seconds)

    def pop_request(self) -> Optional[PipelineOptions]:
        return self.claim_request()

    def request_cancel(self) -> None:
        self.cancel_path.touch()

    def clear_cancel(self) -> None:
        self.cancel_path.unlink(missing_ok=True)

    def cancel_requested(self) -> bool:
        return self.cancel_path.exists()

    def snapshot_for_api(self) -> Dict[str, Any]:
        snapshot = self.read_state()
        return {
            **snapshot.to_dict(),
            "logs": self.read_logs(),
        }

    def clear_session(self, work_dir: Optional[Path] = None) -> JobSnapshot:
        root = work_dir or get_work_dir()
        output_dir: Optional[Path] = None
        zip_path: Optional[Path] = None

        with self._lock:
            snapshot = self._read_state_unlocked()
            if snapshot.running:
                raise JobClearError("Cannot clear session while a prediction is running.")
            if self.request_path.is_file():
                raise JobClearError("Cannot clear session while a prediction is starting.")

            if snapshot.output_dir:
                output_dir = Path(snapshot.output_dir)
            if snapshot.zip_path:
                zip_path = Path(snapshot.zip_path)

            self.log_path.write_text("", encoding="utf-8")
            self.cancel_path.unlink(missing_ok=True)
            self.request_path.unlink(missing_ok=True)
            self._write_state_unlocked(JobSnapshot())

        if output_dir is not None:
            _safe_delete_path(output_dir, root)
        elif zip_path is not None:
            _safe_delete_path(zip_path, root)

        return JobSnapshot()


def _allowed_output_roots(work_dir: Path) -> list[Path]:
    return [(work_dir / "data" / "output").resolve()]


def _safe_delete_path(path: Path, work_dir: Path) -> None:
    if not path.exists():
        return

    resolved = path.resolve()
    allowed = _allowed_output_roots(work_dir)
    if not any(root == resolved or root in resolved.parents for root in allowed):
        return

    if resolved.is_dir():
        shutil.rmtree(resolved, ignore_errors=True)
    else:
        resolved.unlink(missing_ok=True)


class JobCancelMonitor:
    def __init__(self, store: JobStore) -> None:
        self.store = store

    def is_set(self) -> bool:
        return self.store.cancel_requested()

    def set(self) -> None:
        self.store.request_cancel()

    def clear(self) -> None:
        self.store.clear_cancel()


def options_to_dict(options: PipelineOptions) -> Dict[str, Any]:
    payload = asdict(options)
    payload["input_file"] = str(options.input_file)
    if options.work_dir is not None:
        payload["work_dir"] = str(options.work_dir)
    else:
        payload["work_dir"] = None
    return payload


def options_from_dict(payload: Dict[str, Any]) -> PipelineOptions:
    work_dir = payload.get("work_dir")
    return PipelineOptions(
        input_file=Path(payload["input_file"]),
        outdir=payload.get("outdir", "data/output/Results_Prediction"),
        biotrans_type=payload.get("biotrans_type", "allHuman"),
        nstep=int(payload.get("nstep", 1)),
        cmode=int(payload.get("cmode", 3)),
        phase1=int(payload.get("phase1", 1)),
        phase2=int(payload.get("phase2", 1)),
        phase_gloryx=payload.get("phase_gloryx", "phase_1_and_2"),
        predictor_activate=bool(payload.get("predictor_activate", False)),
        keep_tmp=bool(payload.get("keep_tmp", False)),
        export_elmaven=bool(payload.get("export_elmaven", False)),
        work_dir=Path(work_dir) if work_dir else None,
    )
