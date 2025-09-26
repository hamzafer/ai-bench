"""Benchmark analysis utilities for Comment Sense v2."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

DATA_DIR = Path("data")
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.csv"
BENCHMARK_RESULTS_PATH = DATA_DIR / "benchmark_results.jsonl"
REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

LABEL_FIELDS = ["patient_prioritized", "patient_ready", "patient_short_notice"]


@dataclass
class LabelMetrics:
    field: str
    accuracy: float
    total: int
    correct: int


PRED_NORMALIZATION = {
    True: "true",
    False: "false",
    None: "null",
}


def _normalize_truth(value: Any) -> str:
    if pd.isna(value):
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    str_value = str(value).strip().lower()
    if str_value in {"true", "false", "null"}:
        return str_value
    raise ValueError(f"Unexpected truth label: {value!r}")


def _load_truth() -> pd.DataFrame:
    truth_df = pd.read_csv(GROUND_TRUTH_PATH)
    for field in LABEL_FIELDS:
        truth_df[field] = truth_df[field].apply(_normalize_truth)
    truth_df["availability_mode"] = truth_df["availability_periods"].apply(
        lambda value: "list" if value not in {"null", "None", "[]"} else "null"
    )
    return truth_df


def _load_predictions() -> pd.DataFrame:
    records: List[Dict[str, Any]] = []
    with BENCHMARK_RESULTS_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            raw = json.loads(line)
            response = raw["response"].get("en", {})
            record = {
                "id": raw["id"],
                "pred_patient_prioritized": PRED_NORMALIZATION.get(response.get("patient_prioritized"), "unknown"),
                "pred_patient_ready": PRED_NORMALIZATION.get(response.get("patient_ready"), "unknown"),
                "pred_patient_short_notice": PRED_NORMALIZATION.get(response.get("patient_short_notice"), "unknown"),
                "pred_availability_mode": "list" if response.get("availability_periods") else "null",
                "reasoning": response.get("reasoning", ""),
            }
            records.append(record)
    return pd.DataFrame(records)


def _prepare_dataset() -> pd.DataFrame:
    truth_df = _load_truth()
    preds_df = _load_predictions()
    merged = truth_df.merge(preds_df, on="id", how="inner", validate="one_to_one")
    for field in LABEL_FIELDS:
        merged[f"match_{field}"] = merged[field] == merged[f"pred_{field}"]
    merged["match_availability_mode"] = merged["availability_mode"] == merged["pred_availability_mode"]
    return merged


def _compute_metrics(dataset: pd.DataFrame) -> List[LabelMetrics]:
    metrics: List[LabelMetrics] = []
    for field in LABEL_FIELDS:
        correct = int(dataset[f"match_{field}"].sum())
        total = int(dataset.shape[0])
        metrics.append(LabelMetrics(field, correct / total if total else 0.0, total, correct))
    correct = int(dataset["match_availability_mode"].sum())
    total = int(dataset.shape[0])
    metrics.append(LabelMetrics("availability_mode", correct / total if total else 0.0, total, correct))
    return metrics


def _plot_metric_overview(metrics: List[LabelMetrics]) -> None:
    df = pd.DataFrame(
        {
            "field": [m.field for m in metrics],
            "accuracy": [m.accuracy for m in metrics],
            "correct": [m.correct for m in metrics],
            "total": [m.total for m in metrics],
        }
    )
    plt.figure(figsize=(8, 4))
    sns.barplot(data=df, x="field", y="accuracy", palette="viridis")
    plt.ylim(0, 1)
    plt.title("Accuracy per field")
    plt.ylabel("Accuracy")
    plt.xlabel("")
    for idx, row in df.iterrows():
        plt.text(idx, row["accuracy"] + 0.02, f"{row['correct']}/{row['total']}", ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig(REPORT_DIR / "accuracy_overview.png", dpi=200)
    plt.close()


def _plot_confusion(dataset: pd.DataFrame, field: str) -> None:
    truth = dataset[field]
    pred = dataset[f"pred_{field}"]
    labels = ["true", "false", "null"]
    confusion = pd.crosstab(truth, pred, dropna=False).reindex(index=labels, columns=labels, fill_value=0)
    plt.figure(figsize=(4.5, 4))
    sns.heatmap(confusion, annot=True, fmt="d", cmap="Blues", cbar=False)
    plt.title(f"Confusion matrix: {field}")
    plt.ylabel("Ground truth")
    plt.xlabel("Prediction")
    plt.tight_layout()
    plt.savefig(REPORT_DIR / f"confusion_{field}.png", dpi=200)
    plt.close()


def _save_failures(dataset: pd.DataFrame) -> None:
    failures = dataset[
        (~dataset["match_patient_prioritized"]) |
        (~dataset["match_patient_ready"]) |
        (~dataset["match_patient_short_notice"]) |
        (~dataset["match_availability_mode"])
    ].copy()
    if failures.empty:
        return
    columns = [
        "id",
        "comment_text",
        "patient_prioritized",
        "pred_patient_prioritized",
        "patient_ready",
        "pred_patient_ready",
        "patient_short_notice",
        "pred_patient_short_notice",
        "availability_mode",
        "pred_availability_mode",
        "reasoning",
    ]
    failures.to_csv(REPORT_DIR / "benchmark_failures.csv", columns=columns, index=False)


def main() -> None:
    dataset = _prepare_dataset()
    metrics = _compute_metrics(dataset)
    _plot_metric_overview(metrics)
    for field in LABEL_FIELDS:
        _plot_confusion(dataset, field)
    _save_failures(dataset)
    summary_path = REPORT_DIR / "benchmark_summary.json"
    summary_payload: Dict[str, Any] = {
        "metrics": [m.__dict__ for m in metrics],
        "failure_count": int((~dataset[[
            "match_patient_prioritized",
            "match_patient_ready",
            "match_patient_short_notice",
            "match_availability_mode",
        ]].all(axis=1)).sum()),
        "total": int(dataset.shape[0]),
        "reports": {
            "accuracy_overview": str((REPORT_DIR / "accuracy_overview.png").resolve()),
            "confusion_matrices": {
                field: str((REPORT_DIR / f"confusion_{field}.png").resolve()) for field in LABEL_FIELDS
            },
            "failures_csv": str((REPORT_DIR / "benchmark_failures.csv").resolve()),
        },
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
