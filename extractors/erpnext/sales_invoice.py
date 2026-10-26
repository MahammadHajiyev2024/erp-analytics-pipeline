"""Extractor for ERPNext Sales Invoice doctype (header + nested line items)."""

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from requests import Session

from common.erpnext import ERPNextError, error_detail, get_session
from extractors.watermark import DEFAULT_STATE_FILE, get_watermark, update_watermark

logger = logging.getLogger(__name__)
PAGE_SIZE = 1000
TIMEOUT_SECONDS = 30


def fetch_sales_invoice_names(
    session: Session,
    base_url: str,
    watermark: str | None = None,
    page_size: int = PAGE_SIZE,
) -> list[str]:
    """Fetch invoice names modified after the watermark, paginating deterministically."""
    endpoint = f"{base_url.rstrip('/')}/api/resource/Sales Invoice"
    filters = []
    if watermark:
        filters.append(["Sales Invoice", "modified", ">", watermark])

    invoice_names: list[str] = []
    limit_start = 0

    while True:
        params: dict[str, Any] = {
            "fields": json.dumps(["name", "modified"]),
            "order_by": "modified asc, name asc",
            "limit_start": limit_start,
            "limit_page_length": page_size,
        }
        if filters:
            params["filters"] = json.dumps(filters)

        response = session.get(endpoint, params=params, timeout=TIMEOUT_SECONDS)
        if not response.ok:
            raise ERPNextError(f"Listing Sales Invoice failed: {error_detail(response)}")

        batch = response.json().get("data", [])
        if not batch:
            break

        invoice_names.extend(row["name"] for row in batch)
        limit_start += len(batch)

        if len(batch) < page_size:
            break

    return invoice_names


def fetch_sales_invoice_doc(
    session: Session,
    base_url: str,
    invoice_name: str,
) -> dict[str, Any]:
    """Fetch complete Sales Invoice document including nested child items."""
    endpoint = f"{base_url.rstrip('/')}/api/resource/Sales Invoice/{invoice_name}"
    response = session.get(endpoint, timeout=TIMEOUT_SECONDS)
    if not response.ok:
        raise ERPNextError(
            f"Fetching Sales Invoice '{invoice_name}' failed: {error_detail(response)}"
        )
    return response.json().get("data", {})


def run_sales_invoice_extraction(
    output_dir: Path = Path("data/landing/sales_invoice"),
    watermark_path: Path = DEFAULT_STATE_FILE,
    max_records: int | None = None,
) -> Path | None:
    """Incrementally extract full Sales Invoice documents and write to JSONL."""
    load_dotenv()
    api_key = os.getenv("ERPNEXT_API_KEY")
    api_secret = os.getenv("ERPNEXT_API_SECRET")
    base_url = os.getenv("ERPNEXT_URL", "http://localhost:8080")

    if not api_key or not api_secret:
        raise ValueError("Missing ERPNEXT_API_KEY or ERPNEXT_API_SECRET in environment")

    session = get_session(api_key, api_secret)
    watermark = get_watermark("Sales Invoice", state_file=watermark_path)

    logger.info("Fetching invoice list (watermark: %s)...", watermark)
    invoice_names = fetch_sales_invoice_names(session, base_url, watermark=watermark)
    if not invoice_names:
        logger.info("No new or modified Sales Invoices since watermark: %s", watermark)
        return None

    if max_records:
        invoice_names = invoice_names[:max_records]

    total_invoices = len(invoice_names)
    logger.info("Extracting %d full Sales Invoice documents...", total_invoices)

    batch_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    file_path = output_dir / f"sales_invoice_{run_timestamp}_{batch_id[:8]}.jsonl"

    latest_modified = ""
    extracted_count = 0

    part_path = file_path.with_suffix(".jsonl.part")
    with open(part_path, "w", encoding="utf-8") as f:
        part_path = file_path.with_suffix(".jsonl.part")
    with open(part_path, "w", encoding="utf-8") as f:
        for idx, name in enumerate(invoice_names, start=1):
            doc = fetch_sales_invoice_doc(session, base_url, name)
            if not doc:
                raise ERPNextError(f"Empty document returned for Sales Invoice {name}")

            doc["_ingested_at"] = ingested_at
            doc["_source"] = "erpnext/sales_invoice"
            doc["_batch_id"] = batch_id

            f.write(json.dumps(doc) + "\n")
            extracted_count += 1

            if doc.get("modified", "") > latest_modified:
                latest_modified = doc["modified"]

            if idx % 5000 == 0 or idx == total_invoices:
                logger.info("Extracted %d / %d Sales Invoices", idx, total_invoices)

    part_path.replace(file_path)
    if extracted_count > 0 and latest_modified:
        update_watermark(
            "Sales Invoice",
            latest_modified,
            extracted_count,
            ingested_at,
            state_file=watermark_path,
        )

    logger.info("Extracted %d Sales Invoices to %s", extracted_count, file_path)
    return file_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    staged = run_sales_invoice_extraction()
    print("Staged file:", staged)
