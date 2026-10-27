"""Generic extractor for ERPNext documents with child tables (one GET per document)."""

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from requests import Session

from common.erpnext import TIMEOUT_SECONDS, ERPNextError, error_detail, get_session
from extractors.watermark import DEFAULT_STATE_FILE, get_watermark, update_watermark

logger = logging.getLogger(__name__)
PAGE_SIZE = 1000
PROGRESS_EVERY = 5000


def slug(doctype: str) -> str:
    """Return the snake_case name used for files, folders, and _source ("sales_invoice")."""
    return doctype.lower().replace(" ", "_")


def fetch_document_names(
    session: Session,
    base_url: str,
    doctype: str,
    watermark: str | None = None,
    page_size: int = PAGE_SIZE,
) -> list[str]:
    """Return names of documents modified after the watermark, paginating deterministically."""
    endpoint = f"{base_url.rstrip('/')}/api/resource/{doctype}"
    filters = [[doctype, "modified", ">", watermark]] if watermark else []

    names: list[str] = []
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
            raise ERPNextError(f"Listing {doctype} failed: {error_detail(response)}")

        batch = response.json().get("data", [])
        names.extend(row["name"] for row in batch)
        limit_start += len(batch)
        if len(batch) < page_size:
            return names


def fetch_document(session: Session, base_url: str, doctype: str, name: str) -> dict[str, Any]:
    """Return one complete document, including its child tables."""
    endpoint = f"{base_url.rstrip('/')}/api/resource/{doctype}/{name}"
    response = session.get(endpoint, timeout=TIMEOUT_SECONDS)
    if not response.ok:
        raise ERPNextError(f"Fetching {doctype} '{name}' failed: {error_detail(response)}")
    return response.json().get("data", {})


def run_document_extraction(
    doctype: str,
    output_dir: Path | None = None,
    watermark_path: Path = DEFAULT_STATE_FILE,
    max_records: int | None = None,
) -> Path | None:
    """Extract documents modified since the watermark to one JSON Lines file.

    Each line is the document exactly as ERPNext returned it, plus _ingested_at,
    _source, and _batch_id. The file is written as .part and renamed only when complete,
    and the watermark moves only after that, so a failed run leaves nothing behind.
    """
    load_dotenv()
    api_key = os.getenv("ERPNEXT_API_KEY")
    api_secret = os.getenv("ERPNEXT_API_SECRET")
    base_url = os.getenv("ERPNEXT_URL", "http://localhost:8080")
    if not api_key or not api_secret:
        raise ValueError("Missing ERPNEXT_API_KEY or ERPNEXT_API_SECRET in environment")

    name_slug = slug(doctype)
    output_dir = output_dir or Path("data/landing") / name_slug
    session = get_session(api_key, api_secret)
    watermark = get_watermark(doctype, state_file=watermark_path)

    logger.info("Listing %s modified after %s...", doctype, watermark)
    names = fetch_document_names(session, base_url, doctype, watermark=watermark)
    if not names:
        logger.info("No new or modified %s since %s", doctype, watermark)
        return None
    if max_records:
        names = names[:max_records]

    batch_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()
    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{name_slug}_{run_timestamp}_{batch_id[:8]}.jsonl"
    part_path = file_path.with_suffix(".jsonl.part")

    latest_modified = ""
    with open(part_path, "w", encoding="utf-8") as f:
        for idx, name in enumerate(names, start=1):
            doc = fetch_document(session, base_url, doctype, name)
            if not doc:
                raise ERPNextError(f"Empty document returned for {doctype} {name}")

            doc["_ingested_at"] = ingested_at
            doc["_source"] = f"erpnext/{name_slug}"
            doc["_batch_id"] = batch_id
            f.write(json.dumps(doc) + "\n")

            latest_modified = max(latest_modified, doc.get("modified", ""))
            if idx % PROGRESS_EVERY == 0 or idx == len(names):
                logger.info("Extracted %d / %d %s", idx, len(names), doctype)

    part_path.replace(file_path)
    update_watermark(doctype, latest_modified, len(names), ingested_at, state_file=watermark_path)
    logger.info("Extracted %d %s to %s", len(names), doctype, file_path)
    return file_path
