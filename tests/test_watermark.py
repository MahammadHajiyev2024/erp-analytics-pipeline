"""Unit tests for watermark state manager."""

from pathlib import Path

from extractors.watermark import get_watermark, load_watermarks, update_watermark


def test_load_watermarks_missing_file(tmp_path: Path) -> None:
    """Returns empty dictionary if watermark file does not exist."""
    state_file = tmp_path / "watermarks.json"
    assert load_watermarks(state_file) == {}


def test_get_watermark_empty(tmp_path: Path) -> None:
    """Returns None when doctype has not been extracted yet."""
    state_file = tmp_path / "watermarks.json"
    assert get_watermark("Customer", state_file) is None


def test_update_and_get_watermark(tmp_path: Path) -> None:
    """Persists watermark entry and reads it back accurately."""
    state_file = tmp_path / "watermarks.json"

    update_watermark(
        doctype="Customer",
        last_modified="2026-10-25 04:13:57.095056",
        records_count=5878,
        extracted_at="2026-10-25T18:45:00Z",
        state_file=state_file,
    )

    assert get_watermark("Customer", state_file) == "2026-10-25 04:13:57.095056"

    # Preserves Customer when adding another doctype
    update_watermark(
        doctype="Item",
        last_modified="2026-10-25 05:00:00.000000",
        records_count=4750,
        extracted_at="2026-10-25T18:46:00Z",
        state_file=state_file,
    )

    assert get_watermark("Customer", state_file) == "2026-10-25 04:13:57.095056"
    assert get_watermark("Item", state_file) == "2026-10-25 05:00:00.000000"
