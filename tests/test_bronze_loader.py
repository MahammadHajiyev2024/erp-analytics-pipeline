"""Unit tests for Databricks bronze loader."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from databricks.sdk.errors import NotFound

from loaders.bronze import upload_to_volume


def test_upload_to_volume(tmp_path: Path) -> None:
    """upload_to_volume streams local file to Databricks volume."""
    test_file = tmp_path / "customer_test.jsonl"
    test_file.write_text('{"name": "12345"}\n', encoding="utf-8")

    mock_client = MagicMock()
    mock_client.files.get_metadata.side_effect = NotFound("not found")

    target_path = upload_to_volume(
        local_file=test_file,
        volume_dir="/Volumes/erp_analytics/bronze/landing/customer",
        client=mock_client,
    )

    assert target_path == "/Volumes/erp_analytics/bronze/landing/customer/customer_test.jsonl"
    assert mock_client.files.upload.call_count == 1
    args, kwargs = mock_client.files.upload.call_args
    assert args[0] == "/Volumes/erp_analytics/bronze/landing/customer/customer_test.jsonl"
    assert kwargs.get("overwrite") is False


def test_upload_skips_file_already_uploaded(tmp_path: Path) -> None:
    """A retried run finds its own file in the volume and does not upload again."""
    test_file = tmp_path / "item_test.jsonl"
    test_file.write_text('{"name": "A"}\n', encoding="utf-8")
    mock_client = MagicMock()
    mock_client.files.get_metadata.return_value = MagicMock(content_length=test_file.stat().st_size)

    target_path = upload_to_volume(test_file, "/Volumes/x/item", client=mock_client)

    assert target_path == "/Volumes/x/item/item_test.jsonl"
    mock_client.files.upload.assert_not_called()


def test_upload_refuses_different_file_with_same_name(tmp_path: Path) -> None:
    """A different file under an existing name raises instead of overwriting."""
    test_file = tmp_path / "item_test.jsonl"
    test_file.write_text('{"name": "A"}\n', encoding="utf-8")
    mock_client = MagicMock()
    mock_client.files.get_metadata.return_value = MagicMock(content_length=999)

    with pytest.raises(ValueError, match="refusing to overwrite"):
        upload_to_volume(test_file, "/Volumes/x/item", client=mock_client)

    mock_client.files.upload.assert_not_called()
