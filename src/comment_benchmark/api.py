"""FastAPI app exposing dataset benchmarking utilities."""
from __future__ import annotations

import csv
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests
from fastapi import FastAPI, HTTPException, Query

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = Path("data")
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.csv"
RESULTS_PATH = DATA_DIR / "benchmark_results.jsonl"
SUMMARY_PATH = Path("reports/benchmark_summary.json")
FAILURES_PATH = Path("reports/benchmark_failures.csv")
ANALYSIS_SCRIPT = ["uv", "run", "python", "scripts/analyze_benchmark.py"]
RUN_SCRIPT = ["uv", "run", "python", "scripts/run_benchmark.py"]
COMMENT_ENDPOINT = "https://hero.deepinsight.internal/api/comment-analysis/analyze"
HEADERS = {"Content-Type": "application/json"}
REQUEST_TIMEOUT = 30

app = FastAPI(title="Comment Benchmark UI API")


def _read_ground_truth() -> List[Dict[str, Any]]:
    if not GROUND_TRUTH_PATH.exists():
        raise HTTPException(status_code=404, detail="Ground truth file not found")
    with GROUND_TRUTH_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_results() -> List[Dict[str, Any]]:
    if not RESULTS_PATH.exists():
        return []
    records: List[Dict[str, Any]] = []
    with RESULTS_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            records.append(json.loads(line))
    return records


def _write_results(records: List[Dict[str, Any]]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_summary() -> Dict[str, Any]:
    if not SUMMARY_PATH.exists():
        return {}
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def _read_failures(limit: int | None = None) -> List[Dict[str, Any]]:
    if not FAILURES_PATH.exists():
        return []
    with FAILURES_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if limit is not None:
        rows = rows[:limit]
    return rows


def _combine_rows() -> List[Dict[str, Any]]:
    truth_rows = _read_ground_truth()
    pred_map: Dict[str, Dict[str, Any]] = {record["id"]: record for record in _read_results()}
    combined: List[Dict[str, Any]] = []
    for idx, row in enumerate(truth_rows, start=1):
        prediction = pred_map.get(row["id"])
        combined.append(
            {
                "id": row["id"],
                "row_number": idx,
                "comment_text": row["comment_text"],
                "truth": {
                    "patient_prioritized": row.get("patient_prioritized"),
                    "patient_ready": row.get("patient_ready"),
                    "patient_short_notice": row.get("patient_short_notice"),
                    "availability_periods": row.get("availability_periods"),
                },
                "prediction": prediction.get("response", {}).get("en") if prediction else None,
                "latency_ms": prediction.get("latency_ms") if prediction else None,
            }
        )
    return combined


@app.get("/api/ground-truth")
def get_ground_truth() -> Dict[str, Any]:
    return {"rows": _read_ground_truth()}


@app.get("/api/results")
def get_results() -> Dict[str, Any]:
    return {"rows": _combine_rows(), "summary": _read_summary()}


@app.post("/api/run-benchmark")
def run_benchmark() -> Dict[str, Any]:
    try:
        subprocess.run(RUN_SCRIPT, check=True)
        subprocess.run(ANALYSIS_SCRIPT, check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - surfaced via HTTP error
        raise HTTPException(status_code=500, detail=f"Benchmark execution failed: {exc}") from exc
    return {"summary": _read_summary()}


@app.get("/api/summary")
def get_summary() -> Dict[str, Any]:
    return {"summary": _read_summary()}


@app.get("/api/failures")
def get_failures(limit: int | None = 50) -> Dict[str, Any]:
    return {"rows": _read_failures(limit=limit)}


def _call_comment_analysis(comment_text: str) -> Dict[str, Any]:
    start_ts = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    response = requests.post(
        COMMENT_ENDPOINT,
        headers=HEADERS,
        json={"comment_text": comment_text},
        timeout=REQUEST_TIMEOUT,
        verify=False,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    end_ts = datetime.now(timezone.utc).isoformat()
    response.raise_for_status()
    return {
        "response": response.json(),
        "status_code": response.status_code,
        "latency_ms": elapsed_ms,
        "start_time": start_ts,
        "end_time": end_ts,
    }


def _update_result_record(records: List[Dict[str, Any]], new_record: Dict[str, Any]) -> List[Dict[str, Any]]:
    filtered = [record for record in records if record["id"] != new_record["id"]]
    filtered.append(new_record)
    # Keep ordering by row_number if we have it available
    return sorted(filtered, key=lambda rec: rec.get("row_number", 0))


@app.post("/api/run-row/{row_id}")
def run_row(row_id: str) -> Dict[str, Any]:
    truth_rows = _read_ground_truth()
    truth_map = {row["id"]: (idx + 1, row) for idx, row in enumerate(truth_rows)}
    if row_id not in truth_map:
        raise HTTPException(status_code=404, detail="Row not found")

    row_number, truth_row = truth_map[row_id]
    result_payload = _call_comment_analysis(truth_row["comment_text"])

    record = {
        "id": row_id,
        "row_number": row_number,
        "request": {"comment_text": truth_row["comment_text"]},
        "response": result_payload["response"],
        "status_code": result_payload["status_code"],
        "start_time": result_payload["start_time"],
        "end_time": result_payload["end_time"],
        "latency_ms": result_payload["latency_ms"],
    }

    updated_records = _update_result_record(_read_results(), record)
    _write_results(updated_records)

    # Refresh derived reports
    try:
        subprocess.run(ANALYSIS_SCRIPT, check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc

    # Return updated row + new summary
    combined = _combine_rows()
    updated_row = next((item for item in combined if item["id"] == row_id), None)
    return {"row": updated_row, "summary": _read_summary()}


@app.post("/api/run-row/{row_id}/batch")
def run_row_batch(row_id: str, count: int = Query(5, ge=1, le=20)) -> Dict[str, Any]:
    truth_rows = _read_ground_truth()
    truth_map = {row["id"]: (idx + 1, row) for idx, row in enumerate(truth_rows)}
    if row_id not in truth_map:
        raise HTTPException(status_code=404, detail="Row not found")

    row_number, truth_row = truth_map[row_id]
    runs: List[Dict[str, Any]] = []
    for attempt in range(1, count + 1):
        result_payload = _call_comment_analysis(truth_row["comment_text"])
        runs.append(
            {
                "attempt": attempt,
                "latency_ms": result_payload["latency_ms"],
                "status_code": result_payload["status_code"],
                "prediction": result_payload["response"].get("en"),
                "response": result_payload["response"],
            }
        )

    return {
        "row_id": row_id,
        "row_number": row_number,
        "truth": {
            "patient_prioritized": truth_row.get("patient_prioritized"),
            "patient_ready": truth_row.get("patient_ready"),
            "patient_short_notice": truth_row.get("patient_short_notice"),
            "availability_periods": truth_row.get("availability_periods"),
        },
        "runs": runs,
    }
