"""Tests for the generic VARIANT bronze loader (Databricks mocked)."""

from unittest.mock import MagicMock

import pytest

from loaders import bronze

VOLUME_FILE = "/Volumes/erp_analytics/bronze/landing/sales_invoice/test.jsonl"


def mock_cursor(monkeypatch, result):
    """Patch get_connection so every SQL statement goes to a mock cursor."""
    cursor = MagicMock()
    cursor.fetchone.return_value = result
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(bronze, "get_connection", lambda *args, **kwargs: conn)
    return cursor


def test_sales_invoice_load_stores_raw_variant_from_text(monkeypatch):
    cursor = mock_cursor(monkeypatch, result=(66266, 66266, 0))

    inserted = bronze.load_sales_invoices_to_bronze(VOLUME_FILE)

    ddl, copy_into = [call.args[0] for call in cursor.execute.call_args_list]
    assert "CREATE TABLE IF NOT EXISTS bronze.erpnext_sales_invoice" in ddl
    assert "raw VARIANT" in ddl
    assert "COPY INTO bronze.erpnext_sales_invoice" in copy_into
    assert f"FROM '{VOLUME_FILE}'" in copy_into
    assert "FILEFORMAT = TEXT" in copy_into
    assert "::STRING" not in copy_into
    assert inserted == 66266


def test_rerun_of_loaded_file_inserts_nothing(monkeypatch):
    mock_cursor(monkeypatch, result=(0, 0, 0))

    assert bronze.load_sales_invoices_to_bronze(VOLUME_FILE) == 0


@pytest.mark.parametrize(
    ("loader", "table"),
    [
        (bronze.load_customers_to_bronze, "bronze.erpnext_customer"),
        (bronze.load_items_to_bronze, "bronze.erpnext_item"),
        (bronze.load_sales_invoices_to_bronze, "bronze.erpnext_sales_invoice"),
        (bronze.load_purchase_invoices_to_bronze, "bronze.erpnext_purchase_invoice"),
    ],
)
def test_each_doctype_loads_into_its_own_variant_table(monkeypatch, loader, table):
    cursor = mock_cursor(monkeypatch, result=(10, 10, 0))

    assert loader(VOLUME_FILE) == 10

    ddl, copy_into = [call.args[0] for call in cursor.execute.call_args_list]
    assert f"CREATE TABLE IF NOT EXISTS {table} (" in ddl
    assert "raw VARIANT" in ddl
    assert f"COPY INTO {table}\n" in copy_into
