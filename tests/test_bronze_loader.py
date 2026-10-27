"""Unit tests for Databricks bronze loader."""

from pathlib import Path
from unittest.mock import MagicMock

from loaders.bronze import upload_to_volume


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
