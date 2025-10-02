#!/usr/bin/env bash
# Helper script to run the ground truth review tool

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🚀 Starting Ground Truth Review Tool..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 Project: $PROJECT_ROOT"
echo "📝 Data file: data/ground_truth.csv"
echo "💾 Output: data/ground_truth_reviewed.csv"
echo ""
echo "🌐 Translation: Enabled (if GEMINI_API_KEY is set)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if ground truth exists
if [ ! -f "data/ground_truth.csv" ]; then
    echo "❌ Error: data/ground_truth.csv not found!"
    echo ""
    echo "Generate it first by running:"
    echo "  uv run python -m comment_benchmark.synth --generate 50"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found"
    echo "   Translation will be disabled without GEMINI_API_KEY"
    echo ""
fi

# Run streamlit
uv run streamlit run src/comment_benchmark/review.py \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    --server.port=8501

