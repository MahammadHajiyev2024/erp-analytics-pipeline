"""Unit tests for Databricks connection client."""

from unittest.mock import MagicMock, patch

import pytest

from common.databricks import get_connection, get_databricks_config


def test_get_databricks_config_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config parses valid variables and strips https:// prefix."""
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc-test.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/12345")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapitest123")
    monkeypatch.setenv("DATABRICKS_CATALOG", "erp_analytics")

    config = get_databricks_config()
    assert config["server_hostname"] == "dbc-test.cloud.databricks.com"
    assert config["http_path"] == "/sql/1.0/warehouses/12345"
    assert config["access_token"] == "dapitest123"
    assert config["catalog"] == "erp_analytics"


def test_get_databricks_config_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config raises ValueError when required environment variables are absent."""
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_HTTP_PATH", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)

    with pytest.raises(ValueError, match="Missing required Databricks settings"):
        get_databricks_config()


@patch("common.databricks.sql.connect")
def test_get_connection_context_manager(
    mock_connect: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_connection opens and automatically closes the connection."""
    monkeypatch.setenv("DATABRICKS_HOST", "dbc-test.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/12345")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapitest123")
    monkeypatch.setenv("DATABRICKS_CATALOG", "erp_analytics")

    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    with get_connection() as conn:
        assert conn == mock_conn
        mock_connect.assert_called_once_with(
            server_hostname="dbc-test.cloud.databricks.com",
            http_path="/sql/1.0/warehouses/12345",
            access_token="dapitest123",
            catalog="erp_analytics",
        )

    mock_conn.close.assert_called_once()
