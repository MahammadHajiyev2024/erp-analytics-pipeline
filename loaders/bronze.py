"""Databricks bronze layer loader using SDK volume upload and COPY INTO."""

import logging
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

from common.databricks import get_connection

logger = logging.getLogger(__name__)

CUSTOMER_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS bronze.erpnext_customer (
    name STRING,
    customer_name STRING,
    customer_group STRING,
    territory STRING,
    disabled BIGINT,
    creation STRING,
    modified STRING,
    _ingested_at STRING,
    _source STRING,
    _batch_id STRING
)
USING DELTA;
"""

ITEM_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS bronze.erpnext_item (
    name STRING,
    item_code STRING,
    item_name STRING,
    item_group STRING,
    stock_uom STRING,
    disabled BIGINT,
    is_stock_item BIGINT,
    is_sales_item BIGINT,
    is_purchase_item BIGINT,
    standard_rate DOUBLE,
    valuation_rate DOUBLE,
    last_purchase_rate DOUBLE,
    end_of_life STRING,
    creation STRING,
    modified STRING,
    _ingested_at STRING,
    _source STRING,
    _batch_id STRING
)
USING DELTA;
"""

SALES_INVOICE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS bronze.erpnext_sales_invoice (
    name STRING,
    customer STRING,
    customer_name STRING,
    posting_date STRING,
    posting_time STRING,
    due_date STRING,
    docstatus BIGINT,
    is_return BIGINT,
    return_against STRING,
    custom_source_invoice STRING,
    currency STRING,
    conversion_rate DOUBLE,
    total_qty DOUBLE,
    net_total DOUBLE,
    total_taxes_and_charges DOUBLE,
    grand_total DOUBLE,
    outstanding_amount DOUBLE,
    status STRING,
    company STRING,
    items STRING,
    taxes STRING,
    creation STRING,
    modified STRING,
    _ingested_at STRING,
    _source STRING,
    _batch_id STRING
)
USING DELTA;
"""


def upload_to_volume(
    local_file: Path,
    volume_dir: str = "/Volumes/erp_analytics/bronze/landing/customer",
    client: WorkspaceClient | None = None,
) -> str:
    """Upload a local file to a Databricks Unity Catalog volume.

    Returns the target volume path.
    """
    load_dotenv()
    if client is None:
        client = WorkspaceClient()

    target_path = f"{volume_dir.rstrip('/')}/{local_file.name}"
    with open(local_file, "rb") as f:
        client.files.upload(target_path, f, overwrite=True)

    return target_path


def load_customers_to_bronze(volume_path: str) -> None:
    """Ensure bronze.erpnext_customer Delta table exists and load new files via COPY INTO."""
    copy_sql = f"""
    COPY INTO bronze.erpnext_customer
    FROM '{volume_path}'
    FILEFORMAT = JSON
    FORMAT_OPTIONS ('multiline' = 'false');
    """

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(CUSTOMER_TABLE_DDL)
        cursor.execute(copy_sql)


def load_items_to_bronze(volume_path: str) -> None:
    """Ensure bronze.erpnext_item Delta table exists and load via COPY INTO."""
    copy_sql = f"""
    COPY INTO bronze.erpnext_item
    FROM '{volume_path}'
    FILEFORMAT = JSON
    FORMAT_OPTIONS ('multiline' = 'false');
    """

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(ITEM_TABLE_DDL)
        cursor.execute(copy_sql)


def load_sales_invoices_to_bronze(volume_path: str) -> None:
    """Ensure bronze.erpnext_sales_invoice Delta table exists and load via COPY INTO."""
    copy_sql = f"""
    COPY INTO bronze.erpnext_sales_invoice
    FROM '{volume_path}'
    FILEFORMAT = JSON
    FORMAT_OPTIONS ('multiline' = 'false');
    """

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(SALES_INVOICE_TABLE_DDL)
        cursor.execute(copy_sql)
