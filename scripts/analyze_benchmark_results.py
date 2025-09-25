#!/usr/bin/env python3
"""Aggregate benchmark responses and produce summary artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DEFAULT_RAW_PATH = Path("benchmark_outputs/raw_responses.jsonl")
DEFAULT_DATASET_PATH = Path("datasets/comment_benchmark_ground_truth.csv")
DEFAULT_OUTPUT_DIR = Path("benchmark_outputs/analysis")


@dataclass
class ParsedRecord:
    example_id: str
    run: int
    status_code: Optional[int]
    latency_ms: Optional[float]
    ready_expected: Optional[bool]
    short_expected: Optional[bool]
    priority_expected: Optional[bool]
    ready_actual: Optional[bool]
    short_actual: Optional[bool]
    priority_actual: Optional[bool]
    reasoning_en: Optional[str]
    availability: Optional[str]
    error: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "run": self.run,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "ready_expected": self.ready_expected,
            "short_expected": self.short_expected,
            "priority_expected": self.priority_expected,
            "ready_actual": self.ready_actual,
            "short_actual": self.short_actual,
            "priority_actual": self.priority_actual,
            "reasoning_en": self.reasoning_en,
            "availability": self.availability,
            "error": self.error,
        }


def interpret_field(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "null", "none"}:
            return None
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def load_raw_records(raw_path: Path) -> list[ParsedRecord]:
    records: list[ParsedRecord] = []
    with raw_path.open(encoding="utf-8") as fh:
        for line in fh:
            data = json.loads(line)
            payload = data.get("json_payload") or {}
            lang_payload = payload.get("en") or payload
            availability = None
            availability_data = lang_payload.get("availability_periods")
            if isinstance(availability_data, list) and availability_data:
                availability = json.dumps(availability_data, ensure_ascii=False)

            records.append(
                ParsedRecord(
                    example_id=data["example_id"],
                    run=int(data["run"]),
                    status_code=data.get("status_code"),
                    latency_ms=data.get("latency_ms"),
                    ready_expected=interpret_field(data.get("expected", {}).get("patient_ready")),
                    short_expected=interpret_field(data.get("expected", {}).get("patient_short_notice")),
                    priority_expected=interpret_field(data.get("expected", {}).get("patient_prioritized")),
                    ready_actual=interpret_field(lang_payload.get("patient_ready")),
                    short_actual=interpret_field(lang_payload.get("patient_short_notice")),
                    priority_actual=interpret_field(lang_payload.get("patient_prioritized")),
                    reasoning_en=lang_payload.get("reasoning"),
                    availability=availability,
                    error=data.get("error"),
                )
            )
    return records


def compute_metrics(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    df = df.copy()
    df["ready_match"] = df.apply(
        lambda row: row["ready_actual"] == row["ready_expected"], axis=1
    )
    df["short_match"] = df.apply(
        lambda row: row["short_actual"] == row["short_expected"], axis=1
    )
    df["priority_match"] = df.apply(
        lambda row: row["priority_actual"] == row["priority_expected"], axis=1
    )
    df["overall_match"] = (
        df["ready_match"]
        & df["short_match"]
        & df["priority_match"]
    )

    grouped = df.groupby("example_id")
    per_example = (
        grouped.agg(
            runs=("run", "count"),
            ready_accuracy=("ready_match", "mean"),
            short_accuracy=("short_match", "mean"),
            priority_accuracy=("priority_match", "mean"),
            overall_accuracy=("overall_match", "mean"),
            status_codes=("status_code", lambda x: sorted(set(x))),
        )
        .reset_index()
    )

    unique_outcomes = grouped.apply(
        lambda frame: frame[["ready_actual", "short_actual", "priority_actual"]]
        .apply(tuple, axis=1)
        .nunique(),
        include_groups=False,
    )
    per_example = per_example.merge(
        unique_outcomes.rename("unique_outcomes"),
        left_on="example_id",
        right_index=True,
        how="left",
    )
    per_example["is_deterministic"] = per_example["unique_outcomes"].fillna(0).eq(1)

    overall = {
        "total_examples": int(per_example.shape[0]),
        "total_runs": int(df.shape[0]),
        "ready_accuracy": df["ready_match"].mean(),
        "short_accuracy": df["short_match"].mean(),
        "priority_accuracy": df["priority_match"].mean(),
        "overall_accuracy": df["overall_match"].mean(),
        "success_rate": (df["status_code"] == 200).mean(),
        "deterministic_examples": int(per_example["is_deterministic"].sum()),
    }

    return df, per_example, overall


def join_comment_text(per_example: pd.DataFrame, dataset_path: Path) -> pd.DataFrame:
    dataset = pd.read_csv(dataset_path)
    subset = dataset[["example_id", "comment_text", "availability_notes", "notes"]]
    return per_example.merge(subset, on="example_id", how="left")


def export_tables(
    df_runs: pd.DataFrame,
    per_example: pd.DataFrame,
    overall: dict[str, Any],
    output_dir: Path,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}

    runs_path = output_dir / "runs_detailed.csv"
    df_runs.to_csv(runs_path, index=False)
    paths["runs_csv"] = runs_path

    per_example_path = output_dir / "per_example_summary.csv"
    per_example.to_csv(per_example_path, index=False)
    paths["per_example_csv"] = per_example_path

    overall_path = output_dir / "overall_metrics.json"
    overall_path.write_text(json.dumps(overall, indent=2), encoding="utf-8")
    paths["overall_json"] = overall_path

    return paths


def plot_accuracy_bars(overall: dict[str, Any], output_dir: Path) -> Path:
    labels = ["patient_ready", "patient_short_notice", "patient_prioritized", "overall"]
    values = [
        overall["ready_accuracy"],
        overall["short_accuracy"],
        overall["priority_accuracy"],
        overall["overall_accuracy"],
    ]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, values, color="#377eb8")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Accuracy")
    ax.set_title("Overall label accuracy")
    ax.bar_label(bars, labels=[f"{v:.1%}" for v in values])
    fig.tight_layout()
    path = output_dir / "overall_accuracy.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_per_example_hist(per_example: pd.DataFrame, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(per_example["overall_accuracy"], bins=11, range=(0, 1), color="#4daf4a", edgecolor="black")
    ax.set_xlabel("Per-example overall accuracy")
    ax.set_ylabel("Number of examples")
    ax.set_title("Distribution of per-example accuracy")
    fig.tight_layout()
    path = output_dir / "per_example_accuracy_hist.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_latency_distribution(df_runs: pd.DataFrame, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(df_runs["latency_ms"].dropna(), bins=30, color="#984ea3", edgecolor="black")
    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("Number of runs")
    ax.set_title("Latency distribution")
    fig.tight_layout()
    path = output_dir / "latency_distribution.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_determinism(per_example: pd.DataFrame, output_dir: Path) -> Path:
    counts = per_example["is_deterministic"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(
        ["Deterministic" if idx else "Varies" for idx in counts.index],
        counts.values,
        color="#ff7f00",
    )
    ax.set_ylabel("Examples")
    ax.set_title("Determinism across runs")
    ax.bar_label(bars)
    fig.tight_layout()
    path = output_dir / "determinism_counts.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def generate_plots(df_runs: pd.DataFrame, per_example: pd.DataFrame, overall: dict[str, Any], output_dir: Path) -> list[Path]:
    plots = [
        plot_accuracy_bars(overall, output_dir),
        plot_per_example_hist(per_example, output_dir),
        plot_latency_distribution(df_runs, output_dir),
        plot_determinism(per_example, output_dir),
    ]
    return plots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW_PATH)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_raw_records(args.raw)
    if not records:
        print("No records found", file=sys.stderr)
        return 1

    df_runs = pd.DataFrame([record.to_dict() for record in records])
    df_runs, per_example, overall = compute_metrics(df_runs)
    per_example = join_comment_text(per_example, args.dataset)

    table_paths = export_tables(df_runs, per_example, overall, output_dir)
    plot_paths = generate_plots(df_runs, per_example, overall, output_dir)

    print("Saved tables:")
    for name, path in table_paths.items():
        print(f"  {name}: {path}")
    print("Saved plots:")
    for path in plot_paths:
        print(f"  {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
