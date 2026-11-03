"""Unit tests for Supplier extractor and bronze loader."""

from unittest.mock import MagicMock, patch

from loaders.bronze import load_suppliers_to_bronze


@patch("loaders.bronze.get_connection")
def test_load_suppliers_to_bronze(mock_get_conn: MagicMock) -> None:
    """load_suppliers_to_bronze executes DDL and COPY INTO commands."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    load_suppliers_to_bronze("/Volumes/erp_analytics/bronze/landing/supplier/test.jsonl")

    assert mock_cursor.execute.call_count == 2
    executed_statements = [call[0][0] for call in mock_cursor.execute.call_args_list]
    assert "CREATE TABLE IF NOT EXISTS bronze.erpnext_supplier" in executed_statements[0]
    assert "COPY INTO bronze.erpnext_supplier" in executed_statements[1]
