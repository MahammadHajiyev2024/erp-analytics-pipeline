"""Watermark state manager for incremental extraction."""

import json
from pathlib import Path
from typing import Any

DEFAULT_STATE_FILE = Path("data/watermarks.json")


def load_watermarks(state_file: Path = DEFAULT_STATE_FILE) -> dict[str, Any]:
    """Load the state dictionary from disk. Returns empty dict if file does not exist."""
    if not state_file.exists():
        return {}
    with open(state_file, encoding="utf-8") as f:
        return json.load(f)


def get_watermark(doctype: str, state_file: Path = DEFAULT_STATE_FILE) -> str | None:
    """Return the last seen modified timestamp for a DocType, or None if never extracted."""
    state = load_watermarks(state_file)
    entry = state.get(doctype)
    if isinstance(entry, dict):
        return entry.get("last_modified")
    return None


def update_watermark(
    doctype: str,
    last_modified: str,
    records_count: int,
    extracted_at: str,
    state_file: Path = DEFAULT_STATE_FILE,
) -> None:
    """Update and persist the watermark for a DocType."""
    state = load_watermarks(state_file)
    state[doctype] = {
        "last_modified": last_modified,
        "last_extracted_at": extracted_at,
        "records_extracted": records_count,
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
