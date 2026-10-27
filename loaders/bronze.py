"""Loaders for the Databricks bronze layer: upload landing files, then COPY INTO."""

import logging
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from dotenv import load_dotenv

from common.databricks import get_connection

logger = logging.getLogger(__name__)

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
    """Upload a local file to a Databricks Unity Catalog volume, never overwriting.

    A file already in the volume with the same size is treated as an earlier upload of
    the same batch (a retried run) and skipped; a different size raises ValueError.
    Returns the target volume path.
    """
    load_dotenv()
    if client is None:
        client = WorkspaceClient()

    target_path = f"{volume_dir.rstrip('/')}/{local_file.name}"
    local_size = local_file.stat().st_size

    try:
        existing = client.files.get_metadata(target_path)
    except NotFound:
        existing = None

    if existing is not None:
        if existing.content_length == local_size:
            logger.info("%s already uploaded (%d bytes), skipping", target_path, local_size)
            return target_path
        raise ValueError(
            f"{target_path} already exists with {existing.content_length} bytes, "
            f"local file has {local_size}; refusing to overwrite"
        )

    with open(local_file, "rb") as f:
        client.files.upload(target_path, f, overwrite=False)
    return target_path


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


def load_customers_to_bronze(volume_path: str) -> int:
    """Load Customer landing files into bronze.erpnext_customer."""
    return load_variant_to_bronze("bronze.erpnext_customer", volume_path)


def load_items_to_bronze(volume_path: str) -> int:
    """Load Item landing files into bronze.erpnext_item."""
    return load_variant_to_bronze("bronze.erpnext_item", volume_path)


def load_sales_invoices_to_bronze(volume_path: str) -> int:
    """Load Sales Invoice landing files into bronze.erpnext_sales_invoice."""
    return load_variant_to_bronze("bronze.erpnext_sales_invoice", volume_path)


def load_purchase_invoices_to_bronze(volume_path: str) -> int:
    """Load Purchase Invoice landing files into bronze.erpnext_purchase_invoice."""
    return load_variant_to_bronze("bronze.erpnext_purchase_invoice", volume_path)


def load_stock_ledger_entries_to_bronze(volume_path: str) -> int:
    """Load Stock Ledger Entry landing files into bronze.erpnext_stock_ledger_entry."""
    return load_variant_to_bronze("bronze.erpnext_stock_ledger_entry", volume_path)
