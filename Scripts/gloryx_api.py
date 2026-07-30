#!/usr/bin/env python3
"""Call the public GLORYx REST API and write a MetaTox-compatible CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

API_BASE = "https://nerdd.univie.ac.at/api"
DEFAULT_TIMEOUT = 120
POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 3600


class GloryxApiError(RuntimeError):
    pass


def _request_json(
    method: str,
    url: str,
    *,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    if params:
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}?{query}"

    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        encoded = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
        body = encoded
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GloryxApiError(f"GLORYx HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GloryxApiError(f"GLORYx request failed for {url}: {exc}") from exc

    if not raw.strip():
        raise GloryxApiError(f"GLORYx returned an empty response for {url}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GloryxApiError(f"GLORYx returned non-JSON data for {url}: {raw[:300]}") from exc


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
    try:
        payload = _request_json(
            "GET",
            f"{API_BASE}/gloryx/jobs",
            params={"inputs": [smiles], "metabolism_phase": phase},
        )
        return _extract_job_id(payload)
    except GloryxApiError:
        payload = _request_json(
            "POST",
            f"{API_BASE}/gloryx/jobs",
            data={"inputs": [smiles], "metabolism_phase": phase},
        )
        return _extract_job_id(payload)


def _wait_for_job(job_id: str) -> Dict[str, Any]:
    deadline = time.time() + MAX_WAIT_SECONDS
    while time.time() < deadline:
        payload = _request_json("GET", f"{API_BASE}/jobs/{job_id}")
        status = str(payload.get("status", "")).lower()
        if status == "completed":
            return payload
        if status in {"failed", "error", "cancelled", "canceled"}:
            raise GloryxApiError(f"GLORYx job {job_id} finished with status '{status}': {payload!r}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise GloryxApiError(f"GLORYx job {job_id} did not complete within {MAX_WAIT_SECONDS} seconds")


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

        if total_pages is not None:
            if page >= total_pages:
                break
            page += 1
            continue

        break

    return results


def _result_row(result: Dict[str, Any]) -> Optional[List[str]]:
    smiles = (
        result.get("metabolite_smiles")
        or result.get("smiles")
        or result.get("Metabolite_SMILES")
        or result.get("metabolite_SMILES")
    )
    if not smiles:
        return None

    score = result.get("score", "")
    pathway = (
        result.get("pathway")
        or result.get("reaction")
        or result.get("transformation")
        or result.get("reaction_name")
        or ""
    )
    return [str(smiles), str(score), str(pathway)]


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
    _wait_for_job(job_id)
    raw_results = _fetch_results(job_id)
    rows = [row for row in (_result_row(item) for item in raw_results) if row]
    write_csv(output_path, rows)
    print(f"GLORYx wrote {len(rows)} metabolite(s) to {output_path}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Query GLORYx and export a MetaTox CSV.")
    parser.add_argument("--phase", required=True, choices=["phase_1", "phase_2", "phase_1_and_2"])
    parser.add_argument("--smile", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        return run_gloryx(args.smile.strip(), args.phase, args.output)
    except GloryxApiError as exc:
        print(f"WARNING: {exc}", file=sys.stderr)
        write_empty_csv(args.output)
        print(f"GLORYx wrote an empty result file to {args.output}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
