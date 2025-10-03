# Reviewing Ground Truth with Label Studio

Label Studio provides a collaborative interface for auditing and correcting
`data/ground_truth.csv`. This guide shows how to export tasks, configure the
labeling UI, review records, and import the results back into CSV form.

## 1. Install Label Studio (separate virtual environment recommended)

```bash
python3 -m venv .ls-env
source .ls-env/bin/activate

pip install --upgrade pip
pip install label-studio
```

> Alternatively, use Docker or another environment manager – follow the
> [official quick start](https://labelstud.io/guide/quick_start/).

## 2. Export tasks from the ground-truth CSV

From the repository root:

```bash
uv run python scripts/export_labelstudio.py \
  --input data/ground_truth.csv \
  --output data/labelstudio/tasks.json
```

- The script reads the CSV and writes Label Studio-ready task objects.
- `availability_periods` values are parsed as JSON when possible.
- The JSON can be imported directly into a Label Studio project
  ("Tasks" → "Upload Tasks").

## 3. Configure the labeling interface

Use the template stored in `labelstudio/comment_sense_config.xml`.

1. In Label Studio project settings, open **Labeling Interface**.
2. Switch to **XML** mode and paste the file contents.
3. Save the configuration.

The UI provides three single-choice fields (prioritized/ready/short notice)
and a text area for editing availability JSON.

## 4. Review data in Label Studio

- Create a project (e.g., “Comment Sense v2 Review”).
- Import `data/labelstudio/tasks.json`.
- Annotate each record using the configured interface.
- Export results when finished (JSON format recommended).

## 5. Import annotations back into CSV

Convert Label Studio’s export into a reviewed CSV with:

```bash
uv run python scripts/import_labelstudio.py \
  --export data/labelstudio/export.json \
  --source data/ground_truth.csv \
  --output data/ground_truth_reviewed_labelstudio.csv
```

- The script expects the export format produced by Label Studio’s **JSON**
  export (the default “Label Studio JSON” option).
- It merges annotations with the original rows by record `id` (stored under
  `meta.id`).
- Output CSV columns match the original schema so the rest of the pipeline
  can consume it directly.

## Tips

- Keep Label Studio and the Streamlit reviewer in sync by designating a
  single “source of truth” file – e.g., copy the imported CSV to
  `data/ground_truth_reviewed.csv` before running benchmarks.
- Translation via Gemini remains available in the Streamlit tool. Use it if
  annotators in Label Studio need reference translations (e.g., embed
  translations manually or keep the Streamlit session open alongside).
- Store Label Studio exports under `data/labelstudio/` (ignored by Git) to
  keep the repository clean.

## Useful commands

```bash
# Launch Label Studio (from .ls-env)
label-studio

# Export tasks again after regenerating ground truth
typically when you run synth.py
uv run python scripts/export_labelstudio.py

# Import annotations after review
uv run python scripts/import_labelstudio.py
```

Label Studio docs: <https://labelstud.io/guide/quick_start/>
