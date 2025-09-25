#!/usr/bin/env python3
"""Analyze variability of the comment analysis endpoint.

The script executes the endpoint multiple times, stores raw responses,
computes summary tables, and generates simple graphs so we can gauge how
stable the returned payload is for a fixed prompt.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx
import matplotlib
import pandas as pd

matplotlib.use("Agg")  # headless backend for server environments
import matplotlib.pyplot as plt  # noqa: E402  (after backend selection)


API_URL = "https://hero.deepinsight.internal/api/comment-analysis/analyze"
DEFAULT_COMMENT = (
    "Kan komme på kort varsel dersom vi får en avlysning. Bor i nærheten."
)


@dataclass
class RequestResult:
    run_index: int
    status_code: Optional[int]
    latency_ms: Optional[float]
    json_payload: Optional[dict[str, Any]]
    text_payload: Optional[str]
    error: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": self.run_index,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "json_payload": self.json_payload,
            "text_payload": self.text_payload,
            "error": self.error,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Number of times to call the endpoint (default: 10)",
    )
    parser.add_argument(
        "--comment",
        type=str,
        default=DEFAULT_COMMENT,
        help="Comment text to send in every request",
    )
    parser.add_argument(
        "--cookie",
        type=str,
        default=None,
        help="Cookie header value. Falls back to --cookie-file or AUTH_COOKIE env.",
    )
    parser.add_argument(
        "--cookie-file",
        type=Path,
        default=Path("auth_token.txt"),
        help="File containing a cookie header value (default: auth_token.txt)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis_outputs"),
        help="Directory to store tables, plots, and raw captures.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Enable TLS verification (disabled by default to mirror test.py)",
    )
    return parser.parse_args()


def resolve_cookie(arg_cookie: Optional[str], cookie_file: Path) -> Optional[str]:
    if arg_cookie:
        return arg_cookie.strip()

    env_cookie = os.getenv("AUTH_COOKIE")
    if env_cookie:
        return env_cookie.strip()

    if cookie_file and cookie_file.exists():
        contents = cookie_file.read_text().strip()
        if contents:
            return contents

    return None


def flatten_availability(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, (str, bytes)):
        return str(value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, Iterable):
        normalized = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(json.dumps(item, sort_keys=True))
            else:
                normalized.append(str(item))
        return " | ".join(normalized)
    return str(value)


def normalize_payload(payload: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    data = payload.get("en", payload)
    result: dict[str, Any] = {
        "patient_ready": data.get("patient_ready"),
        "patient_short_notice": data.get("patient_short_notice"),
        "patient_prioritized": data.get("patient_prioritized"),
        "reasoning": data.get("reasoning"),
        "availability_periods": flatten_availability(data.get("availability_periods")),
    }

    # Capture error details if present on top-level payloads (e.g. not authenticated)
    if "message" in payload:
        result["error_message"] = payload.get("message")
    if "details" in payload:
        result["error_details"] = payload.get("details")
    return result


def issue_requests(
    runs: int,
    comment: str,
    cookie: Optional[str],
    timeout: float,
    verify: bool,
) -> list[RequestResult]:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie

    results: list[RequestResult] = []

    with httpx.Client(headers=headers, timeout=timeout, verify=verify) as client:
        for i in range(1, runs + 1):
            payload = {"comment_text": comment}
            start = time.perf_counter()
            try:
                response = client.post(API_URL, json=payload)
                latency_ms = (time.perf_counter() - start) * 1000.0
                parsed_json: Optional[dict[str, Any]] = None
                text_payload: Optional[str] = None

                try:
                    parsed_json = response.json()
                except json.JSONDecodeError:
                    text_payload = response.text

                result = RequestResult(
                    run_index=i,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    json_payload=parsed_json,
                    text_payload=text_payload,
                    error=None,
                )
            except httpx.RequestError as exc:  # includes network issues
                latency_ms = (time.perf_counter() - start) * 1000.0
                result = RequestResult(
                    run_index=i,
                    status_code=None,
                    latency_ms=latency_ms,
                    json_payload=None,
                    text_payload=None,
                    error=str(exc),
                )
            results.append(result)
    return results


def build_dataframes(results: list[RequestResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    normalized_rows = []
    error_rows = []

    for result in results:
        base = {
            "run": result.run_index,
            "status_code": result.status_code,
            "latency_ms": result.latency_ms,
        }

        if result.error:
            error_rows.append({**base, "error": result.error})
            continue

        if result.json_payload is not None:
            normalized = normalize_payload(result.json_payload)
            normalized_rows.append({**base, **normalized})
        else:
            normalized_rows.append({**base, "raw_text": result.text_payload})

    df_responses = pd.DataFrame(normalized_rows)
    df_errors = pd.DataFrame(error_rows)
    return df_responses, df_errors


def save_raw_results(results: list[RequestResult], output_dir: Path) -> Path:
    output_path = output_dir / "raw_responses.jsonl"
    with output_path.open("w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row.to_dict(), ensure_ascii=False))
            fh.write("\n")
    return output_path


def export_tables(df_responses: pd.DataFrame, df_errors: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}

    if not df_responses.empty:
        responses_path = output_dir / "responses.csv"
        df_responses.to_csv(responses_path, index=False)
        paths["responses_csv"] = responses_path

        combination_cols = [
            "patient_ready",
            "patient_short_notice",
            "patient_prioritized",
            "availability_periods",
        ]
        combination_counts = (
            df_responses.groupby(combination_cols, dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        combo_path = output_dir / "combination_counts.csv"
        combination_counts.to_csv(combo_path, index=False)
        paths["combination_counts_csv"] = combo_path

        reasoning_counts = (
            df_responses["reasoning"].fillna("<missing>").value_counts().reset_index()
        )
        reasoning_counts.columns = ["reasoning", "count"]
        reasoning_path = output_dir / "reasoning_counts.csv"
        reasoning_counts.to_csv(reasoning_path, index=False)
        paths["reasoning_counts_csv"] = reasoning_path

        status_counts = (
            df_responses["status_code"].fillna("<missing>").value_counts().reset_index()
        )
        status_counts.columns = ["status_code", "count"]
        status_path = output_dir / "status_code_counts.csv"
        status_counts.to_csv(status_path, index=False)
        paths["status_code_counts_csv"] = status_path

    if not df_errors.empty:
        errors_path = output_dir / "errors.csv"
        df_errors.to_csv(errors_path, index=False)
        paths["errors_csv"] = errors_path

    return paths


def plot_value_distribution(
    df: pd.DataFrame,
    column: str,
    output_dir: Path,
    orientation: str = "vertical",
    color: str = "#377eb8",
) -> Optional[Path]:
    if df.empty or column not in df:
        return None

    counts = df[column].fillna("null").value_counts()
    if counts.empty:
        return None

    if orientation == "horizontal":
        fig_height = max(3.0, len(counts) * 0.6)
        fig, ax = plt.subplots(figsize=(8, fig_height))
        counts.sort_values().plot(kind="barh", ax=ax, color=color)
        ax.set_xlabel("Count")
        ax.set_ylabel(column)
        for container in ax.containers:
            ax.bar_label(container)
    else:
        fig, ax = plt.subplots(figsize=(6, 4))
        counts.plot(kind="bar", ax=ax, color=color)
        ax.set_xlabel("Value")
        ax.set_ylabel("Count")
        ax.bar_label(ax.containers[0])

    ax.set_title(f"Distribution of {column}")
    fig.tight_layout()
    path = output_dir / f"{column}_distribution.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_reasoning_counts(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    if df.empty or "reasoning" not in df:
        return None

    counts = df["reasoning"].fillna("<missing>").value_counts()
    fig, ax = plt.subplots(figsize=(8, max(3, len(counts) * 0.4)))
    counts.plot(kind="barh", ax=ax, color="#4daf4a")
    ax.set_title("Reasoning text frequency")
    ax.set_xlabel("Count")
    ax.set_ylabel("Reasoning")
    for container in ax.containers:
        ax.bar_label(container)
    fig.tight_layout()
    path = output_dir / "reasoning_frequency.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_latency(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    if df.empty or "latency_ms" not in df:
        return None

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(df["run"], df["latency_ms"], marker="o", linestyle="-", color="#984ea3")
    ax.set_title("Request latency per run")
    ax.set_xlabel("Run")
    ax.set_ylabel("Latency (ms)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = output_dir / "latency_by_run.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def generate_plots(df_responses: pd.DataFrame, output_dir: Path) -> list[Path]:
    plots = []
    for column, orientation, color in (
        ("patient_ready", "vertical", "#377eb8"),
        ("patient_short_notice", "vertical", "#377eb8"),
        ("patient_prioritized", "vertical", "#377eb8"),
        ("availability_periods", "horizontal", "#ff7f00"),
    ):
        path = plot_value_distribution(df_responses, column, output_dir, orientation, color)
        if path:
            plots.append(path)

    for plot_func in (plot_reasoning_counts, plot_latency):
        path = plot_func(df_responses, output_dir)
        if path:
            plots.append(path)
    return plots


def print_console_report(
    results: list[RequestResult],
    df_responses: pd.DataFrame,
    df_errors: pd.DataFrame,
) -> None:
    total = len(results)
    successes = len(df_responses)
    errors = len(df_errors)

    print("\n--- Endpoint Variability Report ---")
    print(f"Total runs: {total}")
    print(f"Successful responses: {successes}")
    print(f"Errors: {errors}")

    if successes:
        unique_combos = (
            df_responses[
                [
                    "patient_ready",
                    "patient_short_notice",
                    "patient_prioritized",
                    "availability_periods",
                ]
            ]
            .drop_duplicates()
            .shape[0]
        )
        unique_reasonings = df_responses["reasoning"].nunique(dropna=True)
        print(f"Unique structured combinations: {unique_combos}")
        print(f"Unique reasoning strings: {unique_reasonings}")
        print("\nSample responses:\n")
        preview = df_responses.head(5)
        with pd.option_context("display.max_colwidth", 120):
            print(preview)

    if errors:
        print("\nErrors observed:")
        print(df_errors)


def main() -> None:
    args = parse_args()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    cookie = resolve_cookie(args.cookie, args.cookie_file)

    results = issue_requests(
        runs=args.runs,
        comment=args.comment,
        cookie=cookie,
        timeout=args.timeout,
        verify=args.verify,
    )

    df_responses, df_errors = build_dataframes(results)

    raw_path = save_raw_results(results, output_dir)
    table_paths = export_tables(df_responses, df_errors, output_dir)
    plot_paths = generate_plots(df_responses, output_dir)

    print_console_report(results, df_responses, df_errors)

    print("\nArtifacts saved to:")
    print(f"  Raw responses: {raw_path}")
    for name, path in table_paths.items():
        print(f"  {name}: {path}")
    for path in plot_paths:
        print(f"  Plot: {path}")


if __name__ == "__main__":
    main()
