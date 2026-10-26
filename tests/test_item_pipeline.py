"""Unit tests for Item extractor and bronze loader."""

from unittest.mock import MagicMock, patch

from extractors.erpnext.item import extract_items
from loaders.bronze import load_items_to_bronze


def test_extract_items_pagination() -> None:
    """extract_items handles multi-page responses with deterministic sorting."""
    mock_session = MagicMock()

    page_1 = {"data": [{"name": "10001", "modified": "2026-10-25 10:00:00"}]}
    page_2 = {"data": []}

    mock_resp1 = MagicMock()
    mock_resp1.json.return_value = page_1
    mock_resp2 = MagicMock()
    mock_resp2.json.return_value = page_2

    mock_session.get.side_effect = [mock_resp1, mock_resp2]

    records = extract_items(
        session=mock_session,
        base_url="http://localhost:8080",
        watermark="2026-10-24 00:00:00",
        page_size=1,
    )

    assert len(records) == 1
    assert records[0]["name"] == "10001"
    assert mock_session.get.call_count == 2


@patch("loaders.bronze.get_connection")
def test_load_items_to_bronze(mock_get_conn: MagicMock) -> None:
    """load_items_to_bronze executes DDL and COPY INTO commands."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    load_items_to_bronze("/Volumes/erp_analytics/bronze/landing/item/test.jsonl")

    assert mock_cursor.execute.call_count == 2
    executed_statements = [call[0][0] for call in mock_cursor.execute.call_args_list]
    assert "CREATE TABLE IF NOT EXISTS bronze.erpnext_item" in executed_statements[0]
    assert "COPY INTO bronze.erpnext_item" in executed_statements[1]
