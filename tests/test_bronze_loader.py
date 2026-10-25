"""Unit tests for Databricks bronze loader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from loaders.bronze import load_customers_to_bronze, upload_to_volume


def test_upload_to_volume(tmp_path: Path) -> None:
    """upload_to_volume streams local file to Databricks volume."""
    test_file = tmp_path / "customer_test.jsonl"
    test_file.write_text('{"name": "12345"}\n', encoding="utf-8")

    mock_client = MagicMock()

    target_path = upload_to_volume(
        local_file=test_file,
        volume_dir="/Volumes/erp_analytics/bronze/landing/customer",
        client=mock_client,
    )

    assert target_path == "/Volumes/erp_analytics/bronze/landing/customer/customer_test.jsonl"
    assert mock_client.files.upload.call_count == 1
    args, kwargs = mock_client.files.upload.call_args
    assert args[0] == "/Volumes/erp_analytics/bronze/landing/customer/customer_test.jsonl"
    assert kwargs.get("overwrite") is True


@patch("loaders.bronze.get_connection")
def test_load_customers_to_bronze(mock_get_conn: MagicMock) -> None:
    """load_customers_to_bronze runs DDL and COPY INTO commands."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value.__enter__.return_value = mock_conn

    volume_path = "/Volumes/erp_analytics/bronze/landing/customer/customer_test.jsonl"
    load_customers_to_bronze(volume_path)

    # Verify DDL executed then COPY INTO executed
    assert mock_cursor.execute.call_count == 2
    executed_statements = [call[0][0] for call in mock_cursor.execute.call_args_list]

    assert "CREATE TABLE IF NOT EXISTS bronze.erpnext_customer" in executed_statements[0]
    assert "COPY INTO bronze.erpnext_customer" in executed_statements[1]
    assert volume_path in executed_statements[1]
