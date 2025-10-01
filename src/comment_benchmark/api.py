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

FIELD_SPECS = [
    ("patient_prioritized", "Prioritized"),
    ("patient_ready", "Ready"),
    ("patient_short_notice", "Short Notice"),
]

FIELD_SPECS_DICT = {key: label for key, label in FIELD_SPECS}

DETERMINISM_DIR = DATA_DIR / "determinism"

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


def _determinism_path(row_id: str) -> Path:
    return DETERMINISM_DIR / f"{row_id}.jsonl"


def _read_determinism_runs(row_id: str) -> List[Dict[str, Any]]:
    path = _determinism_path(row_id)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _append_determinism_runs(row_id: str, new_runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    existing = _read_determinism_runs(row_id)
    start_count = len(existing)
    DETERMINISM_DIR.mkdir(parents=True, exist_ok=True)
    path = _determinism_path(row_id)
    appended: List[Dict[str, Any]] = []
    with path.open("a", encoding="utf-8") as handle:
        for offset, run in enumerate(new_runs):
            record = {
                "attempt": start_count + offset + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **run,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            appended.append(record)
    return existing + appended


def _normalize_label(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false", "null"}:
            return lowered
        return lowered
    return str(value).strip().lower()


def _normalize_availability(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        return "list" if value else "null"
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "" or stripped.lower() == "null":
            return "null"
        if stripped in {"[]"}:
            return "null"
        return "list"
    return "list"


def _build_determinism_stats(row_id: str, runs: List[Dict[str, Any]], truth_row: Dict[str, Any]) -> Dict[str, Any]:
    total = len(runs)
    if total == 0:
        return {}

    latencies = [float(run["latency_ms"]) for run in runs if isinstance(run.get("latency_ms"), (int, float))]
    latency_stats = None
    if latencies:
        latency_stats = {
            "count": len(latencies),
            "mean_ms": sum(latencies) / len(latencies),
            "min_ms": min(latencies),
            "max_ms": max(latencies),
        }

    field_stats: List[Dict[str, Any]] = []
    for key, label in FIELD_SPECS:
        truth_value = _normalize_label(truth_row.get(key))
        counts: Dict[str, int] = {}
        match_count = 0
        for run in runs:
            prediction = run.get("prediction") or {}
            value = _normalize_label(prediction.get(key))
            counts[value] = counts.get(value, 0) + 1
            if value == truth_value:
                match_count += 1
        distribution = [
            {"value": value, "count": count}
            for value, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]
        field_stats.append(
            {
                "key": key,
                "label": label,
                "truth_value": truth_value,
                "match_count": match_count,
                "total": total,
                "match_rate": match_count / total if total else 0.0,
                "distribution": distribution,
            }
        )

    truth_availability = _normalize_availability(truth_row.get("availability_periods"))
    availability_counts: Dict[str, int] = {}
    availability_match = 0
    for run in runs:
        prediction = run.get("prediction") or {}
        pred_value = _normalize_availability(prediction.get("availability_periods"))
        availability_counts[pred_value] = availability_counts.get(pred_value, 0) + 1
        if pred_value == truth_availability:
            availability_match += 1
    availability_distribution = [
        {"value": value, "count": count}
        for value, count in sorted(availability_counts.items(), key=lambda item: item[1], reverse=True)
    ]
    availability_stats = {
        "label": "Availability",
        "truth_value": truth_availability,
        "match_count": availability_match,
        "total": total,
        "match_rate": availability_match / total if total else 0.0,
        "distribution": availability_distribution,
    }

    return {
        "latency": latency_stats,
        "fields": field_stats,
        "availability": availability_stats,
        "total_runs": total,
    }


def _build_determinism_summary(limit: int | None = None) -> Dict[str, Any]:
    truth_rows = _read_ground_truth()
    summary_rows: List[Dict[str, Any]] = []
    latency_all: List[float] = []
    field_summary: Dict[str, Dict[str, Any]] = {
        key: {"label": label, "match_rates": []} for key, label in FIELD_SPECS
    }
    availability_rates: List[float] = []
    total_runs = 0

    for idx, truth_row in enumerate(truth_rows, start=1):
        row_id = truth_row["id"]
        runs = _read_determinism_runs(row_id)
        if not runs:
            continue
        stats = _build_determinism_stats(row_id, runs, truth_row)
        if not stats:
            continue

        latency_stats = stats.get("latency")
        if latency_stats:
            latency_all.extend(
                [float(run["latency_ms"]) for run in runs if isinstance(run.get("latency_ms"), (int, float))]
            )
        total_runs += len(runs)

        lowest_match_rate = 1.0
        for field in stats.get("fields", []):
            field_summary[field["key"]]["match_rates"].append(field["match_rate"])
            lowest_match_rate = min(lowest_match_rate, field["match_rate"])
        availability = stats.get("availability")
        if availability:
            availability_rates.append(availability["match_rate"])
            lowest_match_rate = min(lowest_match_rate, availability["match_rate"])

        summary_rows.append(
            {
                "row_id": row_id,
                "row_number": idx,
                "comment_text": truth_row.get("comment_text", ""),
                "stats": stats,
                "total_runs": len(runs),
                "lowest_match_rate": lowest_match_rate,
            }
        )

    summary_rows.sort(key=lambda item: item["row_number"])
    if limit is not None:
        rows_payload = summary_rows[:limit]
    else:
        rows_payload = summary_rows

    field_overview: List[Dict[str, Any]] = []
    for key, data in field_summary.items():
        rates = data["match_rates"]
        label = data["label"]
        average_rate = sum(rates) / len(rates) if rates else None
        worst_rate = min(rates) if rates else None
        field_overview.append(
            {
                "key": key,
                "label": label,
                "rows_measured": len(rates),
                "average_match_rate": average_rate,
                "worst_match_rate": worst_rate,
            }
        )

    availability_overview = {
        "label": "Availability",
        "rows_measured": len(availability_rates),
        "average_match_rate": (sum(availability_rates) / len(availability_rates)) if availability_rates else None,
        "worst_match_rate": min(availability_rates) if availability_rates else None,
    }

    overall_latency = None
    if latency_all:
        overall_latency = {
            "mean_ms": sum(latency_all) / len(latency_all),
            "min_ms": min(latency_all),
            "max_ms": max(latency_all),
        }

    return {
        "rows": rows_payload,
        "overall": {
            "total_rows": len(truth_rows),
            "rows_with_runs": len(summary_rows),
            "total_runs": total_runs,
            "latency": overall_latency,
            "fields": field_overview,
            "availability": availability_overview,
        },
    }


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
def run_row_batch(
    row_id: str,
    count: int = Query(5, ge=1, le=20),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    truth_rows = _read_ground_truth()
    truth_map = {row["id"]: (idx + 1, row) for idx, row in enumerate(truth_rows)}
    if row_id not in truth_map:
        raise HTTPException(status_code=404, detail="Row not found")

    row_number, truth_row = truth_map[row_id]
    runs_to_append: List[Dict[str, Any]] = []
    for _ in range(count):
        result_payload = _call_comment_analysis(truth_row["comment_text"])
        runs_to_append.append(
            {
                "latency_ms": result_payload["latency_ms"],
                "status_code": result_payload["status_code"],
                "prediction": result_payload["response"].get("en"),
                "response": result_payload["response"],
                "start_time": result_payload["start_time"],
                "end_time": result_payload["end_time"],
            }
        )

    all_runs = _append_determinism_runs(row_id, runs_to_append)
    stats = _build_determinism_stats(row_id, all_runs, truth_row)
    limited_runs = all_runs[-limit:]

    return {
        "row_id": row_id,
        "row_number": row_number,
        "truth": {
            "patient_prioritized": truth_row.get("patient_prioritized"),
            "patient_ready": truth_row.get("patient_ready"),
            "patient_short_notice": truth_row.get("patient_short_notice"),
            "availability_periods": truth_row.get("availability_periods"),
        },
        "runs": limited_runs,
        "stats": stats,
        "total_runs": len(all_runs),
    }


@app.get("/api/determinism/{row_id}")
def get_determinism_row(row_id: str, limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    truth_rows = _read_ground_truth()
    truth_map = {row["id"]: (idx + 1, row) for idx, row in enumerate(truth_rows)}
    if row_id not in truth_map:
        raise HTTPException(status_code=404, detail="Row not found")

    row_number, truth_row = truth_map[row_id]
    runs = _read_determinism_runs(row_id)
    stats = _build_determinism_stats(row_id, runs, truth_row) if runs else {}
    limited_runs = runs[-limit:] if limit else runs

    return {
        "row_id": row_id,
        "row_number": row_number,
        "truth": {
            "patient_prioritized": truth_row.get("patient_prioritized"),
            "patient_ready": truth_row.get("patient_ready"),
            "patient_short_notice": truth_row.get("patient_short_notice"),
            "availability_periods": truth_row.get("availability_periods"),
        },
        "runs": limited_runs,
        "stats": stats,
        "total_runs": len(runs),
    }


@app.get("/api/determinism-summary")
def get_determinism_summary(limit: int | None = Query(None, ge=1, le=500)) -> Dict[str, Any]:
    return _build_determinism_summary(limit=limit)


@app.post("/api/run-determinism-all")
def run_determinism_all(
    count: int = Query(5, ge=1, le=20),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    truth_rows = _read_ground_truth()
    for truth_row in truth_rows:
        row_id = truth_row["id"]
        runs_to_append: List[Dict[str, Any]] = []
        for _ in range(count):
            result_payload = _call_comment_analysis(truth_row["comment_text"])
            runs_to_append.append(
                {
                    "latency_ms": result_payload["latency_ms"],
                    "status_code": result_payload["status_code"],
                    "prediction": result_payload["response"].get("en"),
                    "response": result_payload["response"],
                    "start_time": result_payload["start_time"],
                    "end_time": result_payload["end_time"],
                }
            )
        if runs_to_append:
            _append_determinism_runs(row_id, runs_to_append)

    summary = _build_determinism_summary(limit=limit)
    return {"summary": summary}
