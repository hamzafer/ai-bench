"""Manual review tool for generated ground truth data with translation support."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# Check if translation is available
try:
    import google.generativeai as genai
    TRANSLATION_AVAILABLE = True
except ImportError:
    TRANSLATION_AVAILABLE = False

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_INPUT_PATH = _PROJECT_ROOT / "data" / "ground_truth.csv"
_PROGRESS_PATH = _PROJECT_ROOT / "data" / "review_progress.json"
_ENV_PATH = _PROJECT_ROOT / ".env"
_CACHE_DIR = _PROJECT_ROOT / "data" / "review_cache"
_TRANSLATION_CACHE_PATH = _CACHE_DIR / "translation_cache.json"
_AI_ASSISTANT_CACHE_PATH = _CACHE_DIR / "ai_assistant_cache.json"


def load_data() -> List[Dict[str, Any]]:
    """Load ground truth CSV into memory."""
    if not _INPUT_PATH.exists():
        st.error(f"Ground truth file not found: {_INPUT_PATH}")
        return []

    rows = []
    with _INPUT_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse boolean fields from CSV strings
            for field in ["patient_prioritized", "patient_ready", "patient_short_notice"]:
                val = row[field].strip().lower()
                if val == "true":
                    row[field] = True
                elif val == "false":
                    row[field] = False
                else:
                    row[field] = None

            # Parse JSON field
            try:
                if row["availability_periods"] and row["availability_periods"].strip():
                    row["availability_periods"] = json.loads(row["availability_periods"])
                else:
                    row["availability_periods"] = None
            except (json.JSONDecodeError, TypeError):
                row["availability_periods"] = None
            rows.append(row)
    return rows


def save_progress(current_index: int, reviewed_ids: List[str]) -> None:
    """Save review progress."""
    _PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    progress = {
        "current_index": current_index,
        "reviewed_ids": reviewed_ids,
    }
    _PROGRESS_PATH.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def load_progress() -> Dict[str, Any]:
    """Load review progress."""
    if not _PROGRESS_PATH.exists():
        return {"current_index": 0, "reviewed_ids": []}
    try:
        return json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"current_index": 0, "reviewed_ids": []}


def save_single_record(record: Dict[str, Any]) -> None:
    """Update a single record in ground_truth.csv by ID."""
    _INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Read all lines from CSV
    with _INPUT_PATH.open("r", encoding="utf-8", newline="") as f:
        lines = f.readlines()

    if not lines:
        return

    # Parse CSV to find the record
    reader = csv.DictReader(lines)
    fieldnames = reader.fieldnames

    # Find and update the matching row
    updated_lines = [lines[0]]  # Keep header
    found = False

    for row in reader:
        if row["id"] == record["id"]:
            # Found the record - update it
            found = True

            def bool_to_csv_str(val):
                if val is True:
                    return "true"
                elif val is False:
                    return "false"
                else:
                    return "null"

            # Build updated row
            updated_row = {
                "id": record["id"],
                "comment_text": record["comment_text"],
                "patient_prioritized": bool_to_csv_str(record["patient_prioritized"]),
                "patient_ready": bool_to_csv_str(record["patient_ready"]),
                "patient_short_notice": bool_to_csv_str(record["patient_short_notice"]),
                "availability_periods": json.dumps(
                    record["availability_periods"], ensure_ascii=False
                ) if record["availability_periods"] is not None else "null"
            }

            # Convert to CSV line
            import io
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writerow(updated_row)
            updated_lines.append(output.getvalue())
        else:
            # Keep original line unchanged
            # Reconstruct from the current reader position
            import io
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writerow(row)
            updated_lines.append(output.getvalue())

    # Write back to file
    with _INPUT_PATH.open("w", encoding="utf-8", newline="") as f:
        f.writelines(updated_lines)


def load_api_key() -> Optional[str]:
    """Load Gemini API key from environment."""
    # Try environment variable first
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    
    # Try .env file
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    
    return None


def load_translation_cache() -> Dict[str, str]:
    """Load translation cache from disk."""
    if not _TRANSLATION_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_TRANSLATION_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_translation_cache(cache: Dict[str, str]) -> None:
    """Save translation cache to disk."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _TRANSLATION_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_ai_assistant_cache() -> Dict[str, str]:
    """Load AI assistant cache from disk."""
    if not _AI_ASSISTANT_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_AI_ASSISTANT_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_ai_assistant_cache(cache: Dict[str, str]) -> None:
    """Save AI assistant cache to disk."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _AI_ASSISTANT_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def translate_text(text: str, model: Optional[Any] = None) -> str:
    """Translate Norwegian text to English using Gemini."""
    if not TRANSLATION_AVAILABLE or model is None:
        return text
    
    # Check cache first
    if "translation_cache" not in st.session_state:
        st.session_state.translation_cache = load_translation_cache()
    
    if text in st.session_state.translation_cache:
        return st.session_state.translation_cache[text]
    
    try:
        prompt = f"""Translate this Norwegian hospital scheduling note to English.

Instructions:
- Keep medical abbreviations as-is (MR, CT, ASA, etc.)
- Maintain the informal/colloquial tone
- Preserve any typos or shorthand in spirit
- Keep it concise
- Only return the translation, no explanations

Norwegian text:
{text}

English translation:"""
        
        response = model.generate_content(prompt)
        translation = response.text.strip()
        
        # Cache it
        st.session_state.translation_cache[text] = translation
        save_translation_cache(st.session_state.translation_cache)
        
        return translation
    except Exception as e:
        return f"[Translation error: {str(e)}]"


def get_translation_model() -> Optional[Any]:
    """Initialize Gemini model for translation."""
    if not TRANSLATION_AVAILABLE:
        return None
    
    api_key = load_api_key()
    if not api_key:
        return None
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        return model
    except Exception as e:
        st.error(f"Failed to initialize translation model: {e}")
        return None


def get_ai_assistant(text: str, current_labels: Dict[str, Any], force_refresh: bool = False) -> str:
    """Get AI analysis of the record using Gemini 2.5 Pro."""
    if not TRANSLATION_AVAILABLE:
        return "AI Assistant unavailable (google-generativeai not installed)"
    
    api_key = load_api_key()
    if not api_key:
        return "AI Assistant unavailable (GEMINI_API_KEY not set)"
    
    # Check cache first (unless force refresh)
    if not force_refresh:
        if "ai_assistant_cache" not in st.session_state:
            st.session_state.ai_assistant_cache = load_ai_assistant_cache()
        
        cache_key = f"{text}_{json.dumps(current_labels, sort_keys=True)}"
        if cache_key in st.session_state.ai_assistant_cache:
            return st.session_state.ai_assistant_cache[cache_key]
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        
        prompt = f"""Analyze this Norwegian hospital scheduling note and verify the labels are correct.

Norwegian text:
{text}

Current labels:
- patient_prioritized: {current_labels.get('patient_prioritized')}
- patient_ready: {current_labels.get('patient_ready')}
- patient_short_notice: {current_labels.get('patient_short_notice')}
- availability_periods: {json.dumps(current_labels.get('availability_periods'), ensure_ascii=False)}

Instructions:
1. Translate the text to English
2. For each label, explain if it's CORRECT or WRONG based on the text
3. If wrong, suggest the correct value
4. Be concise but clear

Format:
**Translation:** [English translation]

**Analysis:**
- patient_prioritized: [CORRECT/WRONG] - [brief explanation]
- patient_ready: [CORRECT/WRONG] - [brief explanation]
- patient_short_notice: [CORRECT/WRONG] - [brief explanation]
- availability_periods: [CORRECT/WRONG] - [brief explanation]

**Recommendation:** [Keep as-is / Change X to Y / etc.]"""

        response = model.generate_content(prompt)
        result = response.text.strip()
        
        # Cache it
        if "ai_assistant_cache" not in st.session_state:
            st.session_state.ai_assistant_cache = load_ai_assistant_cache()
        
        cache_key = f"{text}_{json.dumps(current_labels, sort_keys=True)}"
        st.session_state.ai_assistant_cache[cache_key] = result
        save_ai_assistant_cache(st.session_state.ai_assistant_cache)
        
        return result
    
    except Exception as e:
        return f"AI Assistant error: {str(e)}"


def format_bool_display(value: str) -> str:
    """Format bool for display with icons."""
    if value == "true":
        return "✅ True"
    if value == "false":
        return "❌ False"
    return "⚪ Null"


def main() -> None:
    st.set_page_config(page_title="Ground Truth Reviewer", layout="wide")

    # Custom CSS for better styling and keyboard shortcuts
    st.markdown("""
        <style>
        /* Compact layout - prevent scrolling */
        .main .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            max-height: 100vh;
            overflow: hidden;
        }
        .stButton button {
            width: 100%;
        }
        .stButton button[kind="secondary"] {
            background-color: #4CAF50 !important;
            color: white !important;
        }
        /* Reduce margins/padding */
        .element-container {
            margin-bottom: 0.5rem;
        }
        h1 {
            margin-bottom: 0.5rem !important;
        }
        hr {
            margin: 0.5rem 0 !important;
        }
        </style>
        <script>
        document.addEventListener('keydown', function(e) {
            // Ctrl/Cmd + Right Arrow: Next
            if ((e.ctrlKey || e.metaKey) && e.key === 'ArrowRight') {
                e.preventDefault();
                const nextBtn = Array.from(document.querySelectorAll('button')).find(btn => btn.innerText.includes('Next'));
                if (nextBtn) nextBtn.click();
            }
            // Ctrl/Cmd + Left Arrow: Previous
            if ((e.ctrlKey || e.metaKey) && e.key === 'ArrowLeft') {
                e.preventDefault();
                const prevBtn = Array.from(document.querySelectorAll('button')).find(btn => btn.innerText.includes('Prev'));
                if (prevBtn) prevBtn.click();
            }
            // Ctrl/Cmd + Enter: Mark Correct & Next
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                const correctBtn = Array.from(document.querySelectorAll('button')).find(btn => btn.innerText.includes('Mark Correct'));
                if (correctBtn) correctBtn.click();
            }
        });
        </script>
    """, unsafe_allow_html=True)
    
    st.title("🏥 Comment Sense v2 - Ground Truth Review")
    st.caption("Review and correct AI-generated hospital scheduling notes")
    
    # Initialize translation model
    if "translation_model" not in st.session_state:
        if TRANSLATION_AVAILABLE:
            st.session_state.translation_model = get_translation_model()
            if st.session_state.translation_model:
                st.session_state.translation_enabled = True
            else:
                st.session_state.translation_enabled = False
        else:
            st.session_state.translation_enabled = False
    
    # Load data
    if "data" not in st.session_state:
        st.session_state.data = load_data()
        st.session_state.original_data = [row.copy() for row in st.session_state.data]
    
    if not st.session_state.data:
        st.error("No data to review!")
        st.info(f"Looking for data at: {_INPUT_PATH}")
        return
    
    # Load progress
    if "current_index" not in st.session_state:
        progress = load_progress()
        st.session_state.current_index = progress["current_index"]
        st.session_state.reviewed_ids = set(progress["reviewed_ids"])
    
    data = st.session_state.data
    idx = st.session_state.current_index
    
    # Sidebar settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Translation toggle
        if TRANSLATION_AVAILABLE and st.session_state.translation_model:
            translate_enabled = st.toggle(
                "🌐 Enable Translation",
                value=st.session_state.translation_enabled,
                help="Translate Norwegian text to English using Gemini AI"
            )
            st.session_state.translation_enabled = translate_enabled
        else:
            st.warning("⚠️ Translation unavailable")
            if not TRANSLATION_AVAILABLE:
                st.caption("Install: `pip install google-generativeai`")
            else:
                st.caption("Set GEMINI_API_KEY in .env file")
        
        st.divider()
        
        # Batch processing
        st.header("⚡ Batch Processing")
        
        if st.button("🌐 Pre-translate All Records", use_container_width=True):
            if st.session_state.translation_model:
                progress_bar = st.progress(0, text="Translating records...")
                for i, record in enumerate(data):
                    translate_text(record["comment_text"], st.session_state.translation_model)
                    progress_bar.progress((i + 1) / len(data), text=f"Translated {i + 1}/{len(data)}")
                st.success(f"✅ All {len(data)} records translated and cached!")
            else:
                st.error("Translation model not available")
        
        if st.button("🤖 Pre-analyze All Records (AI)", use_container_width=True):
            if TRANSLATION_AVAILABLE and load_api_key():
                progress_bar = st.progress(0, text="AI analyzing records...")
                for i, record in enumerate(data):
                    current_labels = {
                        "patient_prioritized": record["patient_prioritized"],
                        "patient_ready": record["patient_ready"],
                        "patient_short_notice": record["patient_short_notice"],
                        "availability_periods": record["availability_periods"]
                    }
                    get_ai_assistant(record["comment_text"], current_labels, force_refresh=False)
                    progress_bar.progress((i + 1) / len(data), text=f"Analyzed {i + 1}/{len(data)}")
                st.success(f"✅ All {len(data)} records analyzed and cached!")
            else:
                st.error("AI Assistant not available")
        
        st.caption("💡 Tip: Run batch processing once, then review quickly with cached results")
        
        st.divider()
        
        # Statistics
        st.header("📊 Statistics")
        total = len(data)
        reviewed_count = len(st.session_state.reviewed_ids)
        remaining = total - reviewed_count
        
        st.metric("Total Records", total)
        st.metric("Reviewed", reviewed_count)
        st.metric("Remaining", remaining)
        
        if reviewed_count > 0:
            percent = (reviewed_count / total) * 100
            st.progress(reviewed_count / total, text=f"{percent:.1f}% Complete")
        
        st.divider()
        
        # Quick actions
        st.header("🚀 Quick Actions")
        if st.button("💾 Save All Changes", use_container_width=True):
            # Save all reviewed records
            for rec in st.session_state.data:
                if rec.get("reviewed"):
                    save_single_record(rec)
            st.success(f"✅ Saved reviewed records to:\n`{_INPUT_PATH.name}`\n\nCommit with git!")
        
        if st.button("🔄 Reset Progress", use_container_width=True):
            st.session_state.current_index = 0
            st.session_state.reviewed_ids = set()
            save_progress(0, [])
            st.success("Progress reset!")
            st.rerun()
        
    
    # Main content
    # Navigation
    col1, col2, col3, col4, col5, col6 = st.columns([1, 1, 1, 1.5, 1, 2])

    with col1:
        if st.button("⏮️ First", disabled=idx == 0):
            st.session_state.current_index = 0
            st.rerun()

    with col2:
        if st.button("⬅️ Prev", disabled=idx == 0):
            st.session_state.current_index = max(0, idx - 1)
            st.rerun()

    with col3:
        if st.button("➡️ Next", disabled=idx >= len(data) - 1):
            st.session_state.current_index = min(len(data) - 1, idx + 1)
            st.rerun()

    with col4:
        jump_to = st.number_input(
            "Jump to record:",
            min_value=1,
            max_value=len(data),
            value=idx + 1,
            key="jump_input"
        )
        if st.button("🎯 Go"):
            st.session_state.current_index = jump_to - 1
            st.rerun()

    with col5:
        # Filter options
        filter_option = st.selectbox(
            "Filter:",
            ["All", "Unreviewed Only", "Reviewed Only"],
            key="filter"
        )

    with col6:
        st.info(f"📍 Record **{idx + 1}** of **{len(data)}**")

    # Visual overview of all records (collapsed by default)
    with st.expander("📊 View All Records Grid (Click to Expand)", expanded=False):
        st.caption("🟢 Green = Reviewed  •  ⚪ Gray = Unreviewed  •  🔴 Red = Current")

        # Create grid of buttons
        cols_per_row = 20
        for row_start in range(0, len(data), cols_per_row):
            cols = st.columns(cols_per_row)
            for i in range(cols_per_row):
                record_idx = row_start + i
                if record_idx >= len(data):
                    break

                with cols[i]:
                    record_id = data[record_idx]["id"]
                    is_reviewed = record_id in st.session_state.reviewed_ids
                    is_current = record_idx == idx

                    label = f"**{record_idx + 1}**" if is_current else str(record_idx + 1)

                    if is_current:
                        button_type = "primary"
                    elif is_reviewed:
                        button_type = "secondary"
                    else:
                        button_type = "tertiary"

                    if st.button(
                        label,
                        key=f"jump_{record_idx}",
                        type=button_type,
                        use_container_width=True,
                        help=f"Record {record_idx + 1} - {'✅ Reviewed' if is_reviewed else '⚪ Unreviewed'}"
                    ):
                        st.session_state.current_index = record_idx
                        st.rerun()

    # Current record
    if idx >= len(data):
        st.warning("⚠️ No more records!")
        return

    record = data[idx]
    is_reviewed = record["id"] in st.session_state.reviewed_ids

    # Review status indicator
    if is_reviewed:
        st.success("✅ **This record has been reviewed**")
    else:
        st.info("👁️ **Reviewing...**")
    
    st.divider()
    
    # Display section with translation
    col_text_left, col_text_right = st.columns(2)
    
    with col_text_left:
        st.subheader("🇳🇴 Original")
        st.markdown(f"""
        <div style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; border: 1px solid #ddd;">
            <p style="color: #000; font-size: 14px; line-height: 1.4; margin: 0;">
                {record["comment_text"]}
            </p>
        </div>
        """, unsafe_allow_html=True)

    with col_text_right:
        st.subheader("🇬🇧 Translation")
        if st.session_state.translation_enabled and st.session_state.translation_model:
            with st.spinner("Translating..."):
                translation = translate_text(
                    record["comment_text"],
                    st.session_state.translation_model
                )
            st.markdown(f"""
            <div style="background-color: #e8f5e9; padding: 10px; border-radius: 5px; border: 1px solid #4CAF50;">
                <p style="color: #000; font-size: 14px; line-height: 1.4; margin: 0;">
                    {translation}
                </p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("💡 Enable translation in sidebar")
    
    st.divider()
    
    # AI Assistant Section
    with st.expander("🤖 AI Assistant - Get Gemini 2.5 Pro Analysis", expanded=False):
        st.caption("Click 'Analyze' to get AI verification of labels with explanations")
        
        # Check if analysis already exists in cache
        current_labels = {
            "patient_prioritized": record["patient_prioritized"],
            "patient_ready": record["patient_ready"],
            "patient_short_notice": record["patient_short_notice"],
            "availability_periods": record["availability_periods"]
        }
        
        # Load cache and check
        if "ai_assistant_cache" not in st.session_state:
            st.session_state.ai_assistant_cache = load_ai_assistant_cache()
        
        cache_key = f"{record['comment_text']}_{json.dumps(current_labels, sort_keys=True)}"
        has_cached = cache_key in st.session_state.ai_assistant_cache
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button(
                "🔍 Analyze" if not has_cached else "🔍 Show Cached Analysis",
                use_container_width=True,
                type="primary" if not has_cached else "secondary"
            ):
                with st.spinner("🧠 AI analyzing record..."):
                    analysis = get_ai_assistant(record["comment_text"], current_labels, force_refresh=False)
                    st.session_state[f"ai_analysis_{idx}"] = analysis
        
        with col_btn2:
            if has_cached and st.button("🔄 Re-analyze (Fresh)", use_container_width=True):
                with st.spinner("🧠 AI re-analyzing record..."):
                    analysis = get_ai_assistant(record["comment_text"], current_labels, force_refresh=True)
                    st.session_state[f"ai_analysis_{idx}"] = analysis
        
        if has_cached:
            st.caption("✅ Analysis cached - Click 'Show Cached' for instant results or 'Re-analyze' to refresh")
        
        # Show analysis if exists in session state
        if f"ai_analysis_{idx}" in st.session_state:
            st.markdown("### 🎯 AI Analysis:")
            st.markdown(st.session_state[f"ai_analysis_{idx}"])
    
    st.divider()
    
    # Edit section
    col_left, col_right = st.columns([1.2, 1])
    
    with col_left:
        st.subheader("✏️ Edit Comment")
        
        # Editable comment
        new_comment = st.text_area(
            "Comment text (Norwegian):",
            value=record["comment_text"],
            height=80,
            key=f"comment_edit_{idx}",
            help="Edit the Norwegian text if incorrect"
        )
        
        st.subheader("🏷️ Labels")
        
        # Boolean fields in columns for compact layout
        col_b1, col_b2, col_b3 = st.columns(3)

        # Helper to convert Python bool to string for radio
        def bool_to_str(val):
            if val is True:
                return "true"
            elif val is False:
                return "false"
            else:
                return "null"

        # Helper to convert radio string back to Python bool
        def str_to_bool(val):
            if val == "true":
                return True
            elif val == "false":
                return False
            else:
                return None

        with col_b1:
            st.write("**Patient Prioritized:**")
            prioritized_str = st.radio(
                "patient_prioritized",
                options=["true", "false", "null"],
                index=["true", "false", "null"].index(bool_to_str(record["patient_prioritized"])),
                key=f"prioritized_{idx}",
                label_visibility="collapsed",
                help="Is the patient prioritized for scheduling?"
            )
            st.caption(format_bool_display(prioritized_str))
            prioritized = str_to_bool(prioritized_str)

        with col_b2:
            st.write("**Patient Ready:**")
            ready_str = st.radio(
                "patient_ready",
                options=["true", "false", "null"],
                index=["true", "false", "null"].index(bool_to_str(record["patient_ready"])),
                key=f"ready_{idx}",
                label_visibility="collapsed",
                help="Is the patient ready for operation?"
            )
            st.caption(format_bool_display(ready_str))
            ready = str_to_bool(ready_str)

        with col_b3:
            st.write("**Short Notice:**")
            short_notice_str = st.radio(
                "patient_short_notice",
                options=["true", "false", "null"],
                index=["true", "false", "null"].index(bool_to_str(record["patient_short_notice"])),
                key=f"short_notice_{idx}",
                label_visibility="collapsed",
                help="Can patient come on short notice?"
            )
            st.caption(format_bool_display(short_notice_str))
            short_notice = str_to_bool(short_notice_str)
    
    with col_right:
        st.subheader("📅 Availability Periods")

        availability = record["availability_periods"]

        # Display current as formatted JSON
        if availability:
            st.json(availability, expanded=True)
        else:
            st.info("⚪ No availability periods (null)")

        # Initialize text state
        state_key = f"avail_text_{idx}_{record['id']}"
        if state_key not in st.session_state:
            st.session_state[state_key] = json.dumps(availability, ensure_ascii=False, indent=2) if availability else "null"

        # Template buttons
        st.write("**Quick Templates:**")
        col_t1, col_t2, col_t3 = st.columns(3)

        with col_t1:
            if st.button("➕ Available From", use_container_width=True, key=f"tmpl_avail_{idx}"):
                st.session_state[state_key] = json.dumps([{
                    "type": "available_from",
                    "start_date": "2025-10-01",
                    "end_date": None
                }], ensure_ascii=False, indent=2)
                st.rerun()

        with col_t2:
            if st.button("🚫 Unavailable Between", use_container_width=True, key=f"tmpl_unavail_{idx}"):
                st.session_state[state_key] = json.dumps([{
                    "type": "unavailable_between",
                    "start_date": "2025-06-15",
                    "end_date": "2025-08-20"
                }], ensure_ascii=False, indent=2)
                st.rerun()

        with col_t3:
            if st.button("⚪ Set Null", use_container_width=True, key=f"tmpl_null_{idx}"):
                st.session_state[state_key] = "null"
                st.rerun()

        # Edit as JSON
        st.write("**Edit Availability:**")

        new_availability_str = st.text_area(
            "JSON or 'null':",
            value=st.session_state[state_key],
            height=120,
            key=state_key,
            help="Single item array: available_from (no end_date) OR unavailable_between (with end_date)"
        )

        # Validation preview
        try:
            if new_availability_str.strip().lower() == "null":
                st.success("✅ Valid: null")
            else:
                parsed = json.loads(new_availability_str)
                if isinstance(parsed, list):
                    if len(parsed) == 1:
                        item = parsed[0]
                        if item.get("type") == "available_from":
                            st.success(f"✅ Valid: available_from {item.get('start_date')}")
                        elif item.get("type") == "unavailable_between":
                            st.success(f"✅ Valid: unavailable {item.get('start_date')} to {item.get('end_date')}")
                        else:
                            st.error("❌ type must be 'available_from' or 'unavailable_between'")
                    else:
                        st.error(f"❌ Must have exactly 1 item, got {len(parsed)}")
                else:
                    st.error("❌ Must be array or null")
        except json.JSONDecodeError as e:
            st.error(f"❌ Invalid JSON: {str(e)}")
    
    # Action buttons
    st.divider()
    col_action1, col_action2, col_action3 = st.columns(3)

    with col_action1:
        if st.button("✅ Save & Next", type="primary", use_container_width=True, key="save_next"):
            # Parse and save changes (or keep as-is if no edits)
            try:
                # Update record
                record["comment_text"] = new_comment
                record["patient_prioritized"] = prioritized
                record["patient_ready"] = ready
                record["patient_short_notice"] = short_notice

                # Parse availability
                if new_availability_str.strip().lower() == "null":
                    record["availability_periods"] = None
                else:
                    parsed_avail = json.loads(new_availability_str)
                    if not isinstance(parsed_avail, list):
                        st.error("❌ Availability must be an array or null!")
                        st.stop()
                    record["availability_periods"] = parsed_avail

                record["reviewed"] = True
                st.session_state.reviewed_ids.add(record["id"])

                # Auto-save this record to CSV
                save_single_record(record)

                next_idx = idx + 1
                save_progress(next_idx, list(st.session_state.reviewed_ids))

                if idx < len(data) - 1:
                    st.session_state.current_index = next_idx
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"❌ Invalid JSON in availability_periods: {str(e)}")
        st.caption("⌨️ Ctrl+Enter")

    with col_action2:
        if st.button("⏭️ Skip", use_container_width=True):
            # Move to next without marking as reviewed
            if idx < len(data) - 1:
                st.session_state.current_index = idx + 1
                st.rerun()

    with col_action3:
        if st.button("🗑️ Delete", use_container_width=True):
            # Confirm deletion
            if st.session_state.get("confirm_delete") != record["id"]:
                st.session_state.confirm_delete = record["id"]
                st.warning("⚠️ Click again to confirm deletion")
                st.stop()

            # Remove record
            st.session_state.data.pop(idx)
            st.session_state.reviewed_ids.discard(record["id"])
            new_idx = min(idx, len(st.session_state.data) - 1)
            save_progress(new_idx, list(st.session_state.reviewed_ids))
            st.session_state.confirm_delete = None
            st.success("🗑️ Record deleted!")
            st.rerun()


if __name__ == "__main__":
    main()
