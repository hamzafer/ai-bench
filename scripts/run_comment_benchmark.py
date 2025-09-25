#!/usr/bin/env python3
"""Run the comment analysis API against a labeled dataset."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

API_URL = "https://hero.deepinsight.internal/api/comment-analysis/analyze"
DEFAULT_DATASET = Path("datasets/comment_benchmark_ground_truth.csv")
DEFAULT_OUTPUT_DIR = Path("benchmark_outputs")


@dataclass
class Example:
    example_id: str
    comment_text: str
    patient_ready: Optional[bool]
    patient_short_notice: Optional[bool]
    patient_prioritized: Optional[bool]

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Example":
        return cls(
            example_id=row["example_id"],
            comment_text=row["comment_text"],
            patient_ready=str_to_bool(row.get("patient_ready")),
            patient_short_notice=str_to_bool(row.get("patient_short_notice")),
            patient_prioritized=str_to_bool(row.get("patient_prioritized")),
        )


@dataclass
class RequestResult:
    example_id: str
    run_index: int
    status_code: Optional[int]
    latency_ms: Optional[float]
    json_payload: Optional[dict[str, Any]]
    text_payload: Optional[str]
    error: Optional[str]
    expected: dict[str, Optional[bool]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "run": self.run_index,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "json_payload": self.json_payload,
            "text_payload": self.text_payload,
            "error": self.error,
            "expected": self.expected,
        }


def str_to_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"", "null", "none"}:
        return None
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Unrecognized boolean literal: {value!r}")


def resolve_cookie(arg_cookie: Optional[str], cookie_file: Path) -> Optional[str]:
    if arg_cookie:
        return arg_cookie.strip()

    env_cookie = os.getenv("AUTH_COOKIE")
    if env_cookie:
        return env_cookie.strip()

    if cookie_file and cookie_file.exists():
        contents = cookie_file.read_text(encoding="utf-8").strip()
        if contents:
            return contents

    return None


def load_examples(csv_path: Path) -> list[Example]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [Example.from_row(row) for row in reader]


def run_requests(
    examples: list[Example],
    runs_per_example: int,
    timeout: float,
    cookie: Optional[str],
    verify: bool,
) -> list[RequestResult]:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie

    results: list[RequestResult] = []

    with httpx.Client(timeout=timeout, headers=headers, verify=verify) as client:
        for example in examples:
            payload = {"comment_text": example.comment_text}
            expected = {
                "patient_ready": example.patient_ready,
                "patient_short_notice": example.patient_short_notice,
                "patient_prioritized": example.patient_prioritized,
            }
            for run_index in range(1, runs_per_example + 1):
                start = time.perf_counter()
                try:
                    response = client.post(API_URL, json=payload)
                    latency_ms = (time.perf_counter() - start) * 1000.0
                    parsed_json: Optional[dict[str, Any]] = None
                    raw_text: Optional[str] = None
                    try:
                        parsed_json = response.json()
                    except json.JSONDecodeError:
                        raw_text = response.text

                    result = RequestResult(
                        example_id=example.example_id,
                        run_index=run_index,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        json_payload=parsed_json,
                        text_payload=raw_text,
                        error=None,
                        expected=expected,
                    )
                except httpx.RequestError as exc:
                    latency_ms = (time.perf_counter() - start) * 1000.0
                    result = RequestResult(
                        example_id=example.example_id,
                        run_index=run_index,
                        status_code=None,
                        latency_ms=latency_ms,
                        json_payload=None,
                        text_payload=None,
                        error=str(exc),
                        expected=expected,
                    )
                results.append(result)
    return results


def save_jsonl(results: list[RequestResult], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for result in results:
            fh.write(json.dumps(result.to_dict(), ensure_ascii=False))
            fh.write("\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--runs", type=int, default=10, help="Number of runs per example")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cookie", type=str, default=None, help="Cookie header value")
    parser.add_argument(
        "--cookie-file",
        type=Path,
        default=Path("auth_token.txt"),
        help="File containing cookie header value",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--verify", action="store_true", help="Enable TLS verification")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    dataset_path: Path = args.dataset
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        examples = load_examples(dataset_path)
    except Exception as exc:  # noqa: BLE001 - surface parsing issues
        print(f"Failed to read dataset: {exc}", file=sys.stderr)
        return 1

    if not examples:
        print("Dataset is empty", file=sys.stderr)
        return 1

    cookie = resolve_cookie(args.cookie, args.cookie_file)
    if not cookie:
        print("Warning: no cookie provided; requests may fail with 401", file=sys.stderr)

    print(
        f"Running {args.runs} iterations for {len(examples)} examples "
        f"({args.runs * len(examples)} total requests)..."
    )

    results = run_requests(
        examples=examples,
        runs_per_example=args.runs,
        timeout=args.timeout,
        cookie=cookie,
        verify=args.verify,
    )

    raw_path = output_dir / "raw_responses.jsonl"
    save_jsonl(results, raw_path)
    print(f"Saved raw responses to {raw_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
