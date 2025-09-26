"""FastAPI app exposing dataset benchmarking utilities."""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException

DATA_DIR = Path("data")
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.csv"
RESULTS_PATH = DATA_DIR / "benchmark_results.jsonl"
SUMMARY_PATH = Path("reports/benchmark_summary.json")
FAILURES_PATH = Path("reports/benchmark_failures.csv")

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
    for row in truth_rows:
        prediction = pred_map.get(row["id"])
        combined.append(
            {
                "id": row["id"],
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
        subprocess.run(["uv", "run", "python", "scripts/run_benchmark.py"], check=True)
        subprocess.run(["uv", "run", "python", "scripts/analyze_benchmark.py"], check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - surfaced via HTTP error
        raise HTTPException(status_code=500, detail=f"Benchmark execution failed: {exc}") from exc
    return {"summary": _read_summary()}


@app.get("/api/summary")
def get_summary() -> Dict[str, Any]:
    return {"summary": _read_summary()}


@app.get("/api/failures")
def get_failures(limit: int | None = 50) -> Dict[str, Any]:
    return {"rows": _read_failures(limit=limit)}
