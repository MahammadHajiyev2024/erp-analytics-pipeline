"""Unit tests for the Customer extractor."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from extractors.erpnext.customer import extract_customers, fetch_customers


def test_fetch_customers_pagination() -> None:
    """fetch_customers paginates until a page with fewer than PAGE_SIZE records is returned."""
    mock_session = MagicMock()

    # Simulate two pages: first page of 1000, second page of 2
    page1 = [{"name": f"CUST-{i}", "modified": "2026-10-01 00:00:00"} for i in range(1000)]
    page2 = [{"name": "CUST-1000", "modified": "2026-10-02 00:00:00"}]

    resp1 = MagicMock()
    resp1.ok = True
    resp1.json.return_value = {"data": page1}

    resp2 = MagicMock()
    resp2.ok = True
    resp2.json.return_value = {"data": page2}

    mock_session.get.side_effect = [resp1, resp2]

    results = fetch_customers(mock_session, "http://erpnext.local")

    assert len(results) == 1001
    assert mock_session.get.call_count == 2


@patch("extractors.erpnext.customer.get_session")
def test_extract_customers_metadata_and_jsonl(
    mock_get_session: MagicMock,
    monkeypatch: MagicMock,
    tmp_path: Path,
) -> None:
    """extract_customers enriches records with metadata and dumps to jsonl."""
    monkeypatch.setenv("ERPNEXT_API_KEY", "test-key")
    monkeypatch.setenv("ERPNEXT_API_SECRET", "test-secret")
    monkeypatch.setenv("ERPNEXT_BASE_URL", "http://erpnext.local")

    mock_session = MagicMock()
    mock_get_session.return_value = mock_session

    sample_records = [
        {"name": "12346", "customer_name": "12346", "modified": "2026-10-25 04:13:57.095056"},
        {"name": "12347", "customer_name": "12347", "modified": "2026-10-25 05:00:00.000000"},
    ]
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = {"data": sample_records}
    mock_session.get.return_value = resp

    output_dir = tmp_path / "landing"
    state_file = tmp_path / "watermarks.json"

    file_path = extract_customers(output_dir=output_dir, state_file=state_file)

    assert file_path is not None
    assert file_path.exists()

    # Verify JSON Lines structure and technical metadata
    lines = file_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2

    row1 = json.loads(lines[0])
    assert row1["name"] == "12346"
    assert row1["_source"] == "erpnext/customer"
    assert "_batch_id" in row1
    assert "_ingested_at" in row1

    # Verify watermark updated to latest modified
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["Customer"]["last_modified"] == "2026-10-25 05:00:00.000000"
    assert state["Customer"]["records_extracted"] == 2
