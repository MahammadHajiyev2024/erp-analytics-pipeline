"""Loaders for the Databricks bronze layer: upload landing files, then COPY INTO."""

import logging
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from dotenv import load_dotenv

from common.databricks import get_connection

logger = logging.getLogger(__name__)

# Key columns copied out of each raw record: column name -> (SQL type, JSON path).
# Every bronze table has its source's key columns, then raw VARIANT and the metadata.
ERPNEXT_KEYS: dict[str, tuple[str, str]] = {
    "name": ("STRING", "$.name"),
    "modified": ("STRING", "$.modified"),
    "docstatus": ("INT", "$.docstatus"),
}
FRED_KEYS: dict[str, tuple[str, str]] = {
    "series_id": ("STRING", "$.series_id"),
    "observation_date": ("STRING", "$.date"),
}


def variant_table_ddl(table: str, keys: dict[str, tuple[str, str]]) -> str:
    """Return CREATE TABLE IF NOT EXISTS for a bronze table with the given key columns."""
    key_columns = "".join(f"    {column} {sql_type},\n" for column, (sql_type, _) in keys.items())
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
{key_columns}    raw VARIANT,
    _ingested_at TIMESTAMP,
    _source STRING,
    _batch_id STRING
)
"""


def variant_copy_into(table: str, volume_path: str, keys: dict[str, tuple[str, str]]) -> str:
    """Return COPY INTO that loads JSON Lines: keys as columns, the whole record as VARIANT."""
    key_selects = ""
    for column, (sql_type, path) in keys.items():
        expression = f"get_json_object(value, '{path}')"
        if sql_type != "STRING":
            expression = f"CAST({expression} AS {sql_type})"
        key_selects += f"        {expression} AS {column},\n"
    return f"""
COPY INTO {table}
FROM (
    SELECT
{key_selects}        parse_json(value) AS raw,
        CAST(get_json_object(value, '$._ingested_at') AS TIMESTAMP) AS _ingested_at,
        get_json_object(value, '$._source') AS _source,
        get_json_object(value, '$._batch_id') AS _batch_id
    FROM '{volume_path}'
)
FILEFORMAT = TEXT
"""


def upload_to_volume(
    local_file: Path,
    volume_dir: str,
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


def load_variant_to_bronze(
    table: str, volume_path: str, keys: dict[str, tuple[str, str]] = ERPNEXT_KEYS
) -> int:
    """Load raw JSON Lines into a bronze table: whole record as VARIANT, keys as columns.

    Returns the number of rows inserted. COPY INTO skips files it has already loaded,
    so a rerun inserts 0.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(variant_table_ddl(table, keys))
        cursor.execute(variant_copy_into(table, volume_path, keys))
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


def load_fred_exchange_rates_to_bronze(volume_path: str) -> int:
    """Load FRED exchange rate landing files into bronze.fred_exchange_rates."""
    return load_variant_to_bronze("bronze.fred_exchange_rates", volume_path, keys=FRED_KEYS)
