"""Extractor for ERPNext Item doctype."""

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from requests import Session

from common.erpnext import get_session
from extractors.watermark import DEFAULT_STATE_FILE, get_watermark, update_watermark

logger = logging.getLogger(__name__)

ITEM_FIELDS = [
    "name",
    "item_code",
    "item_name",
    "item_group",
    "stock_uom",
    "disabled",
    "is_stock_item",
    "is_sales_item",
    "is_purchase_item",
    "standard_rate",
    "valuation_rate",
    "last_purchase_rate",
    "end_of_life",
    "creation",
    "modified",
]


def extract_items(
    session: Session,
    base_url: str,
    watermark: str | None = None,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch items incrementally from ERPNext API with deterministic ordering."""
    endpoint = f"{base_url.rstrip('/')}/api/resource/Item"
    filters = []
    if watermark:
        filters.append(["Item", "modified", ">", watermark])

    records: list[dict[str, Any]] = []
    limit_start = 0

    while True:
        params: dict[str, Any] = {
            "fields": json.dumps(ITEM_FIELDS),
            "order_by": "modified asc, name asc",
            "limit_start": limit_start,
            "limit_page_length": page_size,
        }
        if filters:
            params["filters"] = json.dumps(filters)

        response = session.get(endpoint, params=params)
        response.raise_for_status()
        batch = response.json().get("data", [])

        if not batch:
            break

        records.extend(batch)
        limit_start += len(batch)

        if len(batch) < page_size:
            break

    return records


def run_item_extraction(
    output_dir: Path = Path("data/landing/item"),
    watermark_path: Path = DEFAULT_STATE_FILE,
) -> Path | None:
    """Run incremental item extraction, add metadata, and serialize to JSONL."""
    load_dotenv()
    api_key = os.getenv("ERPNEXT_API_KEY")
    api_secret = os.getenv("ERPNEXT_API_SECRET")
    base_url = os.getenv("ERPNEXT_URL", "http://localhost:8080")

    if not api_key or not api_secret:
        raise ValueError("Missing ERPNEXT_API_KEY or ERPNEXT_API_SECRET in environment")

    session = get_session(api_key, api_secret)
    watermark = get_watermark("Item", state_file=watermark_path)

    items = extract_items(session, base_url, watermark=watermark)
    if not items:
        logger.info("No new or modified items found since watermark: %s", watermark)
        return None

    batch_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()
    for row in items:
        row["_ingested_at"] = ingested_at
        row["_source"] = "erpnext/item"
        row["_batch_id"] = batch_id

    output_dir.mkdir(parents=True, exist_ok=True)
    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    file_path = output_dir / f"item_{run_timestamp}_{batch_id[:8]}.jsonl"

    with open(file_path, "w", encoding="utf-8") as f:
        for row in items:
            f.write(json.dumps(row) + "\n")

    latest_modified = max(r["modified"] for r in items)
    update_watermark(
        "Item",
        latest_modified,
        len(items),
        ingested_at,
        state_file=watermark_path,
    )

    logger.info("Extracted %d items to %s", len(items), file_path)
    return file_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    staged_file = run_item_extraction()
    print("Staged file:", staged_file)
