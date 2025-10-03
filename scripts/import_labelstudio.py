"""Convert Label Studio export JSON back to reviewed ground truth CSV."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_EXPORT = Path("data/labelstudio/export.json")
DEFAULT_OUTPUT = Path("data/ground_truth_reviewed_labelstudio.csv")
DEFAULT_SOURCE = Path("data/ground_truth.csv")

LABEL_FIELDS = [
    ("patient_prioritized", "prioritized"),
    ("patient_ready", "ready"),
    ("patient_short_notice", "short_notice"),
]


def load_tasks(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Label Studio export not found: {path}")
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def load_source_rows(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return {row["id"]: row for row in reader}


def extract_choice(result: Dict[str, Any]) -> Optional[str]:
    value = result.get("value", {})
    choices = value.get("choices")
    if isinstance(choices, list) and choices:
        return str(choices[0])
    return None


def extract_textarea(result: Dict[str, Any]) -> Optional[str]:
    value = result.get("value", {})
    # depending on config, text is under "text" or "textarea"
    texts = value.get("text") or value.get("textareas") or value.get("textarea")
    if isinstance(texts, list) and texts:
        return str(texts[0])
    if isinstance(texts, str):
        return texts
    return None


def parse_annotation(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    annotations = task.get("annotations") or []
    if not annotations:
        return None
    # choose the last completed annotation
    annotation = annotations[-1]
    results = annotation.get("result") or []
    if not results:
        return None

    output: Dict[str, Any] = {}
    for result in results:
        name = result.get("name")
        if not name:
            continue
        if name == "availability":
            text_value = extract_textarea(result)
            output["availability_periods"] = text_value
            continue
        for target_key, expected_name in LABEL_FIELDS:
            if name == expected_name:
                value = extract_choice(result)
                output[target_key] = value
    return output if output else None


def merge_rows(
    source_rows: Dict[str, Dict[str, Any]],
    tasks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for task in tasks:
        meta = task.get("meta") or {}
        data = task.get("data") or {}
        record_id = meta.get("id") or data.get("id")
        if not record_id:
            continue

        base = source_rows.get(record_id, {
            "id": record_id,
            "comment_text": data.get("comment_text", ""),
            "patient_prioritized": data.get("patient_prioritized", "null"),
            "patient_ready": data.get("patient_ready", "null"),
            "patient_short_notice": data.get("patient_short_notice", "null"),
            "availability_periods": data.get("availability_periods", ""),
        })

        annotation = parse_annotation(task)
        if annotation:
            for field, _ in LABEL_FIELDS:
                if annotation.get(field) is not None:
                    base[field] = annotation[field]
            if annotation.get("availability_periods") is not None:
                base["availability_periods"] = annotation["availability_periods"]
        merged.append(base)
    return merged


def write_output(rows: List[Dict[str, Any]], output: Path) -> None:
    if not rows:
        raise ValueError("No annotated rows found in the export")

    fieldnames = [
        "id",
        "comment_text",
        "patient_prioritized",
        "patient_ready",
        "patient_short_notice",
        "availability_periods",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Label Studio annotations back to CSV")
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT, help="Label Studio export JSON")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Original ground truth CSV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Reviewed CSV output")
    args = parser.parse_args()

    tasks = load_tasks(args.export)
    source_rows = load_source_rows(args.source)
    merged_rows = merge_rows(source_rows, tasks)
    write_output(merged_rows, args.output)

    print(f"Wrote {len(merged_rows)} reviewed rows to {args.output}")


if __name__ == "__main__":
    main()
