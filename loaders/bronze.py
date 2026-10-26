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

VARIANT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    name STRING,
    modified STRING,
    docstatus INT,
    raw VARIANT,
    _ingested_at TIMESTAMP,
    _source STRING,
    _batch_id STRING
)
"""

VARIANT_COPY_INTO = """
COPY INTO {table}
FROM (
    SELECT
        get_json_object(value, '$.name') AS name,
        get_json_object(value, '$.modified') AS modified,
        CAST(get_json_object(value, '$.docstatus') AS INT) AS docstatus,
        parse_json(value) AS raw,
        CAST(get_json_object(value, '$._ingested_at') AS TIMESTAMP) AS _ingested_at,
        get_json_object(value, '$._source') AS _source,
        get_json_object(value, '$._batch_id') AS _batch_id
    FROM '{volume_path}'
)
FILEFORMAT = TEXT

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


def load_variant_to_bronze(table: str, volume_path: str) -> int:
    """Load raw JSON Lines into a bronze table: whole record as VARIANT, keys as columns.

    Returns the number of rows inserted. COPY INTO skips files it has already loaded,
    so a rerun inserts 0.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(VARIANT_TABLE_DDL.format(table=table))
        cursor.execute(VARIANT_COPY_INTO.format(table=table, volume_path=volume_path))
        result = cursor.fetchone()
    inserted = result[1] if result else 0
    logger.info("COPY INTO %s inserted %d rows from %s", table, inserted, volume_path)
    return inserted


def load_sales_invoices_to_bronze(volume_path: str) -> int:
    """Load Sales Invoice landing files into bronze.erpnext_sales_invoice."""
    return load_variant_to_bronze("bronze.erpnext_sales_invoice", volume_path)
