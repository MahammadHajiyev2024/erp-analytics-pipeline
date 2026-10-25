"""Customer extractor for ERPNext."""

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from common.erpnext import ERPNextError, error_detail, get_session
from extractors.watermark import DEFAULT_STATE_FILE, get_watermark, update_watermark

PAGE_SIZE = 1000
TIMEOUT_SECONDS = 30
CUSTOMER_FIELDS = [
    "name",
    "customer_name",
    "customer_group",
    "territory",
    "disabled",
    "creation",
    "modified",
]

logger = logging.getLogger(__name__)


def fetch_customers(
    session: requests.Session,
    base_url: str,
    watermark: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch customers modified after watermark, paginating through all pages."""
    records: list[dict[str, Any]] = []
    start = 0
    filters = [["Customer", "modified", ">", watermark]] if watermark else []

    while True:
        params: dict[str, Any] = {
            "fields": json.dumps(CUSTOMER_FIELDS),
            "order_by": "modified asc, name asc",
            "limit_start": start,
            "limit_page_length": PAGE_SIZE,
        }
        if filters:
            params["filters"] = json.dumps(filters)

        response = session.get(
            f"{base_url}/api/resource/Customer",
            params=params,
            timeout=TIMEOUT_SECONDS,
        )
        if not response.ok:
            raise ERPNextError(f"Listing Customer failed: {error_detail(response)}")

        page = response.json().get("data", [])
        records.extend(page)

        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return records


def extract_customers(
    output_dir: Path = Path("data/landing/customer"),
    state_file: Path = DEFAULT_STATE_FILE,
) -> Path | None:
    """Extract Customer records incrementally and stage them to a JSON Lines file.

    Returns the path to the written file, or None if no new records were found.
    """
    load_dotenv()
    base_url = os.getenv("ERPNEXT_BASE_URL", "http://localhost:8080")
    api_key = os.getenv("ERPNEXT_API_KEY")
    api_secret = os.getenv("ERPNEXT_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError("Missing ERPNEXT_API_KEY or ERPNEXT_API_SECRET in environment")

    session = get_session(api_key, api_secret)
    watermark = get_watermark("Customer", state_file=state_file)

    customers = fetch_customers(session, base_url, watermark=watermark)
    if not customers:
        return None

    batch_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()

    # Append bronze metadata columns
    for record in customers:
        record["_ingested_at"] = ingested_at
        record["_source"] = "erpnext/customer"
        record["_batch_id"] = batch_id

    # Stage raw JSON Lines locally
    output_dir.mkdir(parents=True, exist_ok=True)
    run_date = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    file_path = output_dir / f"customer_{run_date}_{batch_id[:8]}.jsonl"

    with open(file_path, "w", encoding="utf-8") as f:
        for record in customers:
            f.write(json.dumps(record) + "\n")

    # Update persistent watermark to the newest modified record seen
    max_modified = max(r["modified"] for r in customers)
    update_watermark(
        doctype="Customer",
        last_modified=max_modified,
        records_count=len(customers),
        extracted_at=ingested_at,
        state_file=state_file,
    )

    return file_path
