# AI Benchmarking

Utilities and scripts for exploring DeepInsight AI benchmarking outputs.

## Getting Started

Clone the repository and install Python dependencies with `uv`:

```bash
uv sync
```

Front-end dependencies live under `ui/`:

```bash
cd ui
npm install
```

## Running the stack

The helper script `scripts/run_dev.sh` boots both services (FastAPI backend
and Vite dev server) in one go:

```bash
./scripts/run_dev.sh
```

By default the API listens on `http://127.0.0.1:8000` and the UI on
`http://127.0.0.1:5173`. Press `Ctrl+C` to stop both processes.

To start the services manually:

```bash
# Backend
uv run uvicorn comment_benchmark.api:app --reload --port 8000

# Frontend
cd ui
npm run dev -- --port 5173
```

## Benchmark pipeline recap

- `src/comment_benchmark/synth.py` – generates the synthetic ground-truth
  dataset (`data/ground_truth.csv`) and caches Gemini calls.
- `scripts/run_benchmark.py` – sends each comment to the internal
  comment-analysis endpoint, capturing latency.
- `scripts/analyze_benchmark.py` – builds plots, CSVs, and summaries under
  `reports/` (including determinism stats when available).

The UI surfaces single-row re-runs and determinism batches. Stored runs
live in `data/determinism/`, enabling inspection of model stability over
time.

## Manual ground-truth review

A Streamlit UI simplifies manual verification of `data/ground_truth.csv`.

```bash
./scripts/run_review.sh
```

The session persists progress (`data/review_progress.json`), supports
optional Norwegian→English translation via Gemini (set
`GEMINI_API_KEY` in `.env`), and exports corrections to
`data/ground_truth_reviewed.csv`. Detailed usage notes live in
`REVIEW_TOOL.md`.
