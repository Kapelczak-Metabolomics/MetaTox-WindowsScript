#!/usr/bin/env python3
"""Call the public GLORYx REST API and write a MetaTox-compatible CSV.

NERDD result fields are metabolite_smiles / priority_score / reaction_type.
Older clients that only looked for score/pathway wrote empty CSVs even when
jobs completed successfully.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

API_BASE = "https://nerdd.univie.ac.at/api"
DEFAULT_TIMEOUT = 120
POLL_INTERVAL_SECONDS = 10
MAX_WAIT_SECONDS = 7200
MAX_HTTP_RETRIES = 8
USER_AGENT = "MetaTox-GLORYx/1.1 (+https://github.com/alexisbourdais/MetaTox)"

COMPLETED_STATUSES = {"completed", "complete", "success", "succeeded", "done"}
FAILED_STATUSES = {"failed", "error", "cancelled", "canceled", "aborted"}


class GloryxApiError(RuntimeError):
    pass


def _request_raw(
    method: str,
    url: str,
    *,
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Tuple[int, bytes, str]:
    request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)

    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_HTTP_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                return response.status, response.read(), content_type
        except urllib.error.HTTPError as exc:
            detail = exc.read()
            # Retry rate limits and transient gateway errors.
            if exc.code in {408, 425, 429, 500, 502, 503, 504} and attempt < MAX_HTTP_RETRIES:
                retry_after = exc.headers.get("Retry-After")
                try:
                    sleep_for = float(retry_after) if retry_after else min(60, 2 ** attempt)
                except ValueError:
                    sleep_for = min(60, 2 ** attempt)
                print(
                    f"GLORYx HTTP {exc.code}; retrying in {sleep_for:.0f}s "
                    f"(attempt {attempt}/{MAX_HTTP_RETRIES})",
                    file=sys.stderr,
                )
                time.sleep(sleep_for)
                last_error = GloryxApiError(
                    f"GLORYx HTTP {exc.code} for {url}: {detail.decode('utf-8', errors='replace')}"
                )
                continue
            raise GloryxApiError(
                f"GLORYx HTTP {exc.code} for {url}: {detail.decode('utf-8', errors='replace')}"
            ) from exc
        except urllib.error.URLError as exc:
            if attempt < MAX_HTTP_RETRIES:
                sleep_for = min(60, 2 ** attempt)
                print(
                    f"GLORYx network error ({exc}); retrying in {sleep_for:.0f}s "
                    f"(attempt {attempt}/{MAX_HTTP_RETRIES})",
                    file=sys.stderr,
                )
                time.sleep(sleep_for)
                last_error = GloryxApiError(f"GLORYx request failed for {url}: {exc}")
                continue
            raise GloryxApiError(f"GLORYx request failed for {url}: {exc}") from exc

    raise GloryxApiError(str(last_error) if last_error else f"GLORYx request failed for {url}")


def _request_json(
    method: str,
    url: str,
    *,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    multipart: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    if params:
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}?{query}"

    body = None
    headers: Dict[str, str] = {}
    if data is not None:
        if multipart:
            # Build a minimal multipart body for NERDD complex job create.
            boundary = f"----MetaToxBoundary{int(time.time() * 1000)}"
            parts: List[bytes] = []
            for key, value in data.items():
                values = value if isinstance(value, list) else [value]
                for item in values:
                    parts.append(
                        (
                            f"--{boundary}\r\n"
                            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                            f"{item}\r\n"
                        ).encode("utf-8")
                    )
            parts.append(f"--{boundary}--\r\n".encode("utf-8"))
            body = b"".join(parts)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        else:
            body = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

    _status, raw, _content_type = _request_raw(method, url, data=body, headers=headers, timeout=timeout)
    text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        raise GloryxApiError(f"GLORYx returned an empty response for {url}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GloryxApiError(f"GLORYx returned non-JSON data for {url}: {text[:300]}") from exc


def _extract_job_id(payload: Any) -> str:
    if isinstance(payload, dict):
        if payload.get("id") is not None:
            return str(payload["id"])
        job = payload.get("job")
        if isinstance(job, dict) and job.get("id") is not None:
            return str(job["id"])
        if payload.get("data") and isinstance(payload["data"], dict) and payload["data"].get("id") is not None:
            return str(payload["data"]["id"])
    raise GloryxApiError(f"GLORYx response did not include a job id: {payload!r}")


def _create_job(smiles: str, phase: str) -> str:
    # Prefer the documented simple-job GET endpoint.
    try:
        payload = _request_json(
            "GET",
            f"{API_BASE}/gloryx/jobs",
            params={"inputs": [smiles], "metabolism_phase": phase},
        )
        return _extract_job_id(payload)
    except GloryxApiError as first_error:
        print(f"GLORYx GET create failed ({first_error}); trying multipart POST...", file=sys.stderr)
        payload = _request_json(
            "POST",
            f"{API_BASE}/gloryx/jobs",
            data={"inputs": [smiles], "metabolism_phase": phase},
            multipart=True,
        )
        return _extract_job_id(payload)


def _queue_info(job_id: str) -> Optional[Dict[str, Any]]:
    try:
        payload = _request_json("GET", f"{API_BASE}/jobs/{job_id}/queue")
        return payload if isinstance(payload, dict) else None
    except GloryxApiError:
        return None


def _wait_for_job(job_id: str) -> Dict[str, Any]:
    deadline = time.time() + MAX_WAIT_SECONDS
    last_status = ""
    while time.time() < deadline:
        payload = _request_json("GET", f"{API_BASE}/jobs/{job_id}")
        status = str(payload.get("status", "")).lower()
        processed = payload.get("num_entries_processed")
        total = payload.get("num_entries_total")
        if status != last_status or status in {"created", "queued", "pending", "running", "processing"}:
            queue = _queue_info(job_id)
            queue_msg = ""
            if queue:
                wait_min = queue.get("waiting_time_minutes")
                active = queue.get("num_active_jobs")
                queue_msg = f" | queue active={active} wait≈{wait_min}min"
            print(
                f"GLORYx job {job_id}: status={status} processed={processed}/{total}{queue_msg}",
                file=sys.stderr,
            )
            last_status = status

        if status in COMPLETED_STATUSES:
            return payload
        if status in FAILED_STATUSES:
            raise GloryxApiError(f"GLORYx job {job_id} finished with status '{status}': {payload!r}")
        time.sleep(POLL_INTERVAL_SECONDS)

    raise GloryxApiError(f"GLORYx job {job_id} did not complete within {MAX_WAIT_SECONDS} seconds")


def _as_smiles(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("smiles", "SMILES", "value", "representation"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _fetch_results(job_id: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    page = 1
    total_pages: Optional[int] = None

    while True:
        payload = _request_json(
            "GET",
            f"{API_BASE}/jobs/{job_id}/results",
            params={"page": page, "incomplete": "true"},
        )
        data = payload.get("data")
        if isinstance(data, list):
            results.extend(item for item in data if isinstance(item, dict))

        pagination = payload.get("pagination")
        if isinstance(pagination, dict) and pagination.get("num_pages_total") is not None:
            total_pages = int(pagination["num_pages_total"])
        elif payload.get("num_pages_total") is not None:
            total_pages = int(payload["num_pages_total"])
        else:
            job = payload.get("job")
            if isinstance(job, dict) and job.get("num_pages_total") is not None:
                total_pages = int(job["num_pages_total"])

        if total_pages is not None:
            if page >= total_pages:
                break
            page += 1
            continue
        break

    return results


def _fetch_output_csv_rows(job_id: str) -> List[List[str]]:
    """Prefer the official CSV export when available."""
    url = f"{API_BASE}/jobs/{job_id}/output.csv"
    try:
        _status, raw, content_type = _request_raw("GET", url, timeout=DEFAULT_TIMEOUT)
    except GloryxApiError as exc:
        print(f"GLORYx CSV export unavailable ({exc})", file=sys.stderr)
        return []

    text = raw.decode("utf-8", errors="replace")
    if "text/html" in content_type.lower() and "<html" in text[:200].lower():
        return []

    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return []

    rows: List[List[str]] = []
    for item in reader:
        smiles = (
            item.get("metabolite_smiles")
            or item.get("Metabolite_SMILES")
            or item.get("smiles")
            or item.get("SMILES")
            or ""
        ).strip()
        if not smiles:
            continue
        # Skip parent rows if the export includes them without reaction info.
        score = (
            item.get("priority_score")
            or item.get("score")
            or item.get("Score")
            or ""
        )
        pathway = (
            item.get("reaction_type")
            or item.get("pathway")
            or item.get("reaction")
            or item.get("Reaction")
            or item.get("reaction_name")
            or ""
        )
        if not pathway and not score:
            # Likely a parent molecule row.
            if item.get("derivative_id") in {None, "", "0", 0}:
                continue
        rows.append([smiles, str(score), str(pathway)])
    return rows


def _result_row(result: Dict[str, Any]) -> Optional[List[str]]:
    smiles = _as_smiles(
        result.get("metabolite_smiles")
        or result.get("Metabolite_SMILES")
        or result.get("metabolite_SMILES")
        or result.get("smiles")
        or result.get("metabolite")
    )
    if not smiles:
        return None

    # Parent / non-derivative rows often lack reaction metadata.
    derivative_id = result.get("derivative_id")
    score = result.get("priority_score", result.get("score", ""))
    pathway = (
        result.get("reaction_type")
        or result.get("pathway")
        or result.get("reaction")
        or result.get("transformation")
        or result.get("reaction_name")
        or ""
    )
    if derivative_id in {None, "", 0, "0"} and not pathway and score in {"", None}:
        return None

    return [str(smiles), str(score if score is not None else ""), str(pathway)]


def write_csv(path: str, rows: List[List[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metabolite_smiles", "score", "pathway"])
        writer.writerows(rows)


def write_empty_csv(path: str) -> None:
    write_csv(path, [])


def run_gloryx(smiles: str, phase: str, output_path: str) -> int:
    job_id = _create_job(smiles, phase)
    print(f"GLORYx job created: {job_id}", file=sys.stderr)
    queue = _queue_info(job_id)
    if queue:
        print(
            f"GLORYx queue: active_jobs={queue.get('num_active_jobs')} "
            f"waiting_time_minutes≈{queue.get('waiting_time_minutes')}",
            file=sys.stderr,
        )
    _wait_for_job(job_id)

    rows = _fetch_output_csv_rows(job_id)
    if not rows:
        raw_results = _fetch_results(job_id)
        rows = [row for row in (_result_row(item) for item in raw_results) if row]
        if not rows and raw_results:
            # Dump keys once to help diagnose schema drift without soft-failing silently.
            sample_keys = sorted({key for item in raw_results[:3] for key in item})
            print(f"GLORYx results present but no metabolite rows mapped. Keys: {sample_keys}", file=sys.stderr)

    write_csv(output_path, rows)
    print(f"GLORYx wrote {len(rows)} metabolite(s) to {output_path}", file=sys.stderr)
    if not rows:
        raise GloryxApiError(
            f"GLORYx job {job_id} completed but produced 0 parseable metabolites. "
            "The NERDD service may be degraded, or the molecule is unsupported."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Query GLORYx and export a MetaTox CSV.")
    parser.add_argument("--phase", required=True, choices=["phase_1", "phase_2", "phase_1_and_2"])
    parser.add_argument("--smile", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--soft-fail",
        action="store_true",
        help="Write an empty CSV and exit 0 on API errors (legacy MetaTox behavior).",
    )
    args = parser.parse_args()

    try:
        return run_gloryx(args.smile.strip(), args.phase, args.output)
    except GloryxApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        write_empty_csv(args.output)
        print(f"GLORYx wrote an empty result file to {args.output}", file=sys.stderr)
        return 0 if args.soft_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
