"""Generate Label Studio tasks from ground truth CSV."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_INPUT = Path("data/ground_truth.csv")
DEFAULT_OUTPUT = Path("data/labelstudio/tasks.json")


def load_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            rows.append(row)
        return rows


def parse_availability(value: str) -> Any:
    text = value.strip()
    if not text or text.lower() in {"null", "none"}:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text  # keep raw string if it's not valid JSON


def build_tasks(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    for row in rows:
        availability = parse_availability(row.get("availability_periods", ""))
        tasks.append(
            {
                "data": {
                    "comment_text": row.get("comment_text", ""),
                    "patient_prioritized": row.get("patient_prioritized"),
                    "patient_ready": row.get("patient_ready"),
                    "patient_short_notice": row.get("patient_short_notice"),
                    "availability_periods": availability,
                },
                "meta": {
                    "id": row.get("id"),
                },
            }
        )
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ground truth to Label Studio tasks")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input CSV path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    args = parser.parse_args()

    rows = load_rows(args.input)
    tasks = build_tasks(rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(tasks)} tasks to {args.output}")


if __name__ == "__main__":
    main()
