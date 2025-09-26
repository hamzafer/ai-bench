"""Send dataset rows to the comment-analysis endpoint and record latency."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATASET_PATH = Path("data/ground_truth.csv")
OUTPUT_PATH = Path("data/benchmark_results.jsonl")
ENDPOINT = "https://hero.deepinsight.internal/api/comment-analysis/analyze"
HEADERS = {"Content-Type": "application/json"}
REQUEST_TIMEOUT = 30
SLEEP_SECONDS = 0.1


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run() -> None:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Missing dataset: {DATASET_PATH}")

    df = pd.read_csv(DATASET_PATH)
    total = len(df)
    print(f"Sending {total} rows to {ENDPOINT}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as outfile:
        for idx, row in df.iterrows():
            payload: Dict[str, str] = {"comment_text": row["comment_text"]}
            start_ts = _iso_now()
            start = time.perf_counter()
            response = requests.post(
                ENDPOINT,
                headers=HEADERS,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                verify=False,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            end_ts = _iso_now()
            response.raise_for_status()
            record = {
                "id": row["id"],
                "row_number": int(idx + 1),
                "request": payload,
                "response": response.json(),
                "status_code": response.status_code,
                "start_time": start_ts,
                "end_time": end_ts,
                "latency_ms": elapsed_ms,
            }
            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
            if SLEEP_SECONDS:
                time.sleep(SLEEP_SECONDS)
    print(f"Wrote results to {OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        sys.exit(1)
