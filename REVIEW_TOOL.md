# Ground Truth Review Tool

A Streamlit-based UI for manually reviewing and correcting AI-generated ground truth data for Comment Sense v2 benchmarking.

## Features

✅ **Norwegian to English Translation** - Built-in translation using Gemini AI  
✅ **Progress Tracking** - Automatically saves your review progress  
✅ **Edit & Validate** - Edit any field with real-time JSON validation  
✅ **Statistics Dashboard** - Track reviewed/remaining records  
✅ **Smart Navigation** - Jump to specific records or skip to next unreviewed  
✅ **Export** - Save reviewed data to new CSV file  

## Quick Start

### 1. Generate Ground Truth Data (if not done already)

```bash
uv run python -m comment_benchmark.synth --generate 50
```

This creates `data/ground_truth.csv` with 50 synthetic records.

### 2. Run the Review Tool

```bash
./scripts/run_review.sh
```

Or directly:

```bash
uv run streamlit run src/comment_benchmark/review.py
```

The tool will open in your browser at http://localhost:8501

### 3. Review the Data

**Navigation:**
- Use ⬅️ **Previous** / ➡️ **Next** buttons
- **Jump to record** - Enter record number and click Go
- Filter by **All** / **Reviewed** / **Unreviewed**

**Translation:**
- Toggle **🌐 Enable Translation** in the sidebar
- Norwegian text will be translated to English on-the-fly
- Translations are cached for speed

**Reviewing:**
- **✅ Mark Correct & Next** - Record is accurate, move to next
- **💾 Save Changes & Next** - Edit fields and save modifications
- **🗑️ Delete Record** - Remove incorrect/bad records
- **⏭️ Skip for Now** - Move on without marking as reviewed

**Editing:**
- Edit the Norwegian comment text if needed
- Change boolean labels (true/false/null) using radio buttons
- Edit availability periods as JSON or set to 'null'
- JSON is validated in real-time

### 4. Export Reviewed Data

Click **💾 Export Reviewed Data** in the sidebar to save:
- Output: `data/ground_truth_reviewed.csv`
- Includes all reviewed records with your corrections
- Ready for benchmarking!

## Understanding the Labels

### Patient Prioritized
- **True**: Patient is marked as urgent/priority (look for "haster", "akutt", "prioritert")
- **False**: Patient is not prioritized
- **Null**: Priority status is not mentioned

### Patient Ready
- **True**: Patient is ready for operation (tests done, preparations complete)
- **False**: Patient is waiting for something (lab results, other procedures)
- **Null**: Readiness is not mentioned

### Patient Short Notice
- **True**: Patient can come on short notice (look for "kort varsel", "kan komme raskt")
- **False**: Patient cannot come on short notice
- **Null**: Short notice availability is not mentioned

### Availability Periods
- **List**: JSON array of date ranges when patient is available
  ```json
  [
    {
      "type": "ledig",
      "start_date": "2025-08-18",
      "end_date": "2025-08-25"
    }
  ]
  ```
- **Null**: No specific availability periods mentioned

## Translation Feature

The tool uses Google's Gemini AI to translate Norwegian text to English in real-time.

**Requirements:**
- `GEMINI_API_KEY` environment variable must be set
- Or add to `.env` file: `GEMINI_API_KEY=your_key_here`

**Features:**
- Real-time translation as you navigate records
- Cached translations (saves API calls)
- Preserves medical abbreviations and informal tone
- Helps non-Norwegian speakers understand the context

**Without Translation:**
The tool works perfectly fine without translation, you just won't see the English version.

## Progress Tracking

Progress is automatically saved to `data/review_progress.json`:
- Current record index
- List of reviewed record IDs

**To reset progress:**
Click **🔄 Reset Progress** in the sidebar

## File Structure

```
data/
├── ground_truth.csv              # Input: AI-generated data
├── ground_truth_reviewed.csv     # Output: Your reviewed data
├── review_progress.json          # Progress tracking
└── translation_cache.json        # Translation cache
```

## Tips

1. **Enable translation first** - Much easier to review if you don't speak Norwegian
2. **Use keyboard efficiently** - Tab between fields, Shift+Enter for newlines
3. **Take breaks** - Progress is saved automatically, resume anytime
4. **Export frequently** - Save reviewed data periodically
5. **Check JSON carefully** - Availability periods must be valid JSON arrays or null
6. **Look for patterns** - After a few records, you'll recognize common phrases

## Troubleshooting

**Translation not working:**
- Check that `GEMINI_API_KEY` is set in `.env` file
- Verify the API key is valid
- Check sidebar for error messages

**Data not loading:**
- Ensure `data/ground_truth.csv` exists
- Run synthesis script first: `uv run python -m comment_benchmark.synth --generate 50`

**Port already in use:**
```bash
uv run streamlit run src/comment_benchmark/review.py --server.port=8502
```

## Keyboard Shortcuts

- **Tab**: Navigate between form fields
- **Shift+Enter**: New line in text areas
- **Enter**: Submit focused button/input

## Examples

### Common Norwegian Phrases

| Norwegian | English | Label Hint |
|-----------|---------|------------|
| "haster" | urgent | patient_prioritized: true |
| "venter på lab" | waiting for lab | patient_ready: false |
| "kort varsel" | short notice | patient_short_notice: true |
| "uke 34" | week 34 | Check availability_periods |
| "ferie 15.07-04.08" | vacation 15.07-04.08 | availability_periods |
| "klar for opr" | ready for operation | patient_ready: true |

## Next Steps

After reviewing:

1. **Use reviewed data for benchmarking:**
   ```bash
   cp data/ground_truth_reviewed.csv data/ground_truth_final.csv
   uv run python scripts/run_benchmark.py
   ```

2. **Analyze quality:**
   ```bash
   uv run python scripts/analyze_benchmark.py
   ```

3. **Generate more data:**
   ```bash
   uv run python -m comment_benchmark.synth --generate 100
   # Then review again
   ```
