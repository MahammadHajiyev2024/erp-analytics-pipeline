"""Generic extractor for ERPNext documents with child tables (one GET per document).

The list API returns no child tables, so each document is fetched on its own. Which
documents to fetch comes from a list of names and `modified` values, paged and windowed
exactly as in the list-only extractor (see `listing.py`):

- **Full load** (no watermark yet): lists names by `name`, the primary key. The watermark
  becomes the newest `modified` that existed when the run started.
- **Incremental load:** lists names by (`modified`, `name`), starting OVERLAP before the
  watermark, and moves the watermark to the newest `modified` in that list.

The watermark always comes from the list, never from the fetched documents. Fetching can
take hours, and a document changed after the list was taken must be read again by the
next run; a watermark taken from the fetched documents could pass over it.

Documents read twice are removed in silver, which keeps the latest version of each `name`.
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from requests import Session

from common.erpnext import TIMEOUT_SECONDS, ERPNextError, error_detail, get_session
from extractors.erpnext.listing import (
    OVERLAP,
    iter_records,
    iter_records_by_name,
    latest_modified,
    overlap_start,
    slug,
)
from extractors.watermark import DEFAULT_STATE_FILE, get_watermark, update_watermark

logger = logging.getLogger(__name__)
PROGRESS_EVERY = 5000
LIST_FIELDS = ("name", "modified")


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
    overlap: timedelta = OVERLAP,
    max_records: int | None = None,
) -> Path | None:
    """Extract new and changed documents to one JSON Lines file; see the module docstring.

    Each line is the document exactly as ERPNext returned it, plus _ingested_at, _source,
    and _batch_id. The file is written as .part and renamed only when complete, and the
    watermark moves only after that, so a failed run leaves nothing behind. If no listed
    document is newer than the watermark (only the overlap would be re-read), nothing is
    fetched and None is returned. A full load cut short by max_records keeps its file but
    does not set the watermark.
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

    if watermark is None:
        new_watermark = latest_modified(session, base_url, doctype)
        if new_watermark is None:
            logger.info("No %s documents", doctype)
            return None
        logger.info("Listing all %s by name (watermark will be %s)...", doctype, new_watermark)
        refs = list(iter_records_by_name(session, base_url, doctype, fields=LIST_FIELDS))
    else:
        since = overlap_start(watermark, overlap)
        logger.info("Listing %s modified since %s (watermark %s)...", doctype, since, watermark)
        refs = list(iter_records(session, base_url, doctype, since=since, fields=LIST_FIELDS))

    truncated = bool(max_records) and len(refs) > max_records
    if truncated:
        refs = refs[:max_records]

    if watermark is not None:
        newer = sum(1 for ref in refs if ref["modified"] > watermark)
        if newer == 0:
            logger.info("No new or modified %s since %s", doctype, watermark)
            return None
        new_watermark = max(watermark, *(ref["modified"] for ref in refs))
    else:
        newer = len(refs)
        if not refs:
            logger.info("No %s documents", doctype)
            return None

    batch_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()
    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{name_slug}_{run_timestamp}_{batch_id[:8]}.jsonl"
    part_path = file_path.with_suffix(".jsonl.part")

    with open(part_path, "w", encoding="utf-8") as f:
        for idx, ref in enumerate(refs, start=1):
            doc = fetch_document(session, base_url, doctype, ref["name"])
            if not doc:
                raise ERPNextError(f"Empty document returned for {doctype} {ref['name']}")

            doc["_ingested_at"] = ingested_at
            doc["_source"] = f"erpnext/{name_slug}"
            doc["_batch_id"] = batch_id
            f.write(json.dumps(doc) + "\n")

            if idx % PROGRESS_EVERY == 0 or idx == len(refs):
                logger.info("Extracted %d / %d %s", idx, len(refs), doctype)

    part_path.replace(file_path)
    if watermark is None and truncated:
        logger.warning("Full load stopped at %d documents; watermark not set", len(refs))
    else:
        update_watermark(doctype, new_watermark, len(refs), ingested_at, state_file=watermark_path)
    logger.info(
        "Extracted %d %s (%d newer than the watermark) to %s", len(refs), doctype, newer, file_path
    )
    return file_path
