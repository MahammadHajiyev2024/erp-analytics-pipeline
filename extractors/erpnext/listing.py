"""Generic list-only extractor for ERPNext doctypes without child tables.

Reads every field from the list API: one request per page of 1,000 records, instead of
one GET per document. Pages use keyset pagination, never offsets, so rows updated during
the run (ERPNext's hourly stock reposting does this) cannot shift unread rows out of a
page, and deep pages cost the same as the first.

- **Full load** (no watermark yet): pages by `name`, the primary key, which is indexed.
  Sorting by `modified` has no index on large tables such as Stock Ledger Entry (11 s
  per page against 0.1 s by name). The watermark becomes the newest `modified` that
  existed when the run started, so rows changed during the run are read again next time.
- **Incremental load:** pages by (`modified`, `name`), starting OVERLAP before the
  watermark, to catch rows that long transactions committed late. ERPNext stores
  `modified` in local time (Europe/London), which repeats an hour when clocks go back in
  October, so the overlap is longer than that hour.

Rows read twice are removed in silver, which keeps the latest version of each `name`.
"""

import json
import logging
import os
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from requests import Session

from common.erpnext import ERPNextError, error_detail, get_session
from extractors.erpnext.documents import slug
from extractors.watermark import DEFAULT_STATE_FILE, get_watermark, update_watermark

logger = logging.getLogger(__name__)
PAGE_SIZE = 1000
LIST_TIMEOUT_SECONDS = 120
OVERLAP = timedelta(hours=2)
PROGRESS_EVERY = 50_000
MODIFIED_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def overlap_start(watermark: str | None, overlap: timedelta = OVERLAP) -> str | None:
    """Return the `modified` value a run starts from: the watermark minus the overlap."""
    if watermark is None:
        return None
    return (datetime.fromisoformat(watermark) - overlap).strftime(MODIFIED_FORMAT)


def fetch_page(
    session: Session,
    base_url: str,
    doctype: str,
    fields: Sequence[str],
    order_by: str,
    page_size: int,
    filters: list[list[Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return the first page of records matching the filters, in the given order."""
    params: dict[str, Any] = {
        "fields": json.dumps(list(fields)),
        "order_by": order_by,
        "limit_start": 0,
        "limit_page_length": page_size,
    }
    if filters:
        params["filters"] = json.dumps(filters)

    response = session.get(
        f"{base_url.rstrip('/')}/api/resource/{doctype}",
        params=params,
        timeout=LIST_TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise ERPNextError(f"Listing {doctype} failed: {error_detail(response)}")
    return response.json().get("data", [])


def latest_modified(session: Session, base_url: str, doctype: str) -> str | None:
    """Return the newest `modified` value of the doctype, or None if it has no records."""
    page = fetch_page(session, base_url, doctype, ["modified"], "modified desc", 1)
    return page[0]["modified"] if page else None


def iter_records(
    session: Session,
    base_url: str,
    doctype: str,
    since: str | None = None,
    fields: Sequence[str] = ("*",),
    page_size: int = PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    """Yield every record with `modified >= since`, using keyset pagination on `modified`.

    Each page starts at the newest `modified` of the previous page; rows of that page
    with exactly that `modified` are skipped when they come back. A row updated during
    the run is yielded again with its new `modified`, which silver deduplicates.
    """
    cursor = since
    seen_at_cursor: set[str] = set()
    while True:
        filters = [[doctype, "modified", ">=", cursor]] if cursor else None
        page = fetch_page(
            session, base_url, doctype, fields, "modified asc, name asc", page_size, filters
        )
        for record in page:
            if record["modified"] == cursor and record["name"] in seen_at_cursor:
                continue
            yield record

        if len(page) < page_size:
            return
        last = page[-1]["modified"]
        if last == cursor:
            raise ERPNextError(
                f"More than {page_size} {doctype} records share modified {last}; "
                "raise the page size"
            )
        seen_at_cursor = {r["name"] for r in page if r["modified"] == last}
        cursor = last


def iter_records_by_name(
    session: Session,
    base_url: str,
    doctype: str,
    fields: Sequence[str] = ("*",),
    page_size: int = PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    """Yield every record of the doctype, using keyset pagination on the primary key."""
    cursor = None
    while True:
        filters = [[doctype, "name", ">", cursor]] if cursor else None
        page = fetch_page(session, base_url, doctype, fields, "name asc", page_size, filters)
        yield from page
        if len(page) < page_size:
            return
        cursor = page[-1]["name"]


def run_list_extraction(
    doctype: str,
    fields: Sequence[str] = ("*",),
    output_dir: Path | None = None,
    watermark_path: Path = DEFAULT_STATE_FILE,
    overlap: timedelta = OVERLAP,
    max_records: int | None = None,
) -> Path | None:
    """Extract new and changed records to one JSON Lines file; see the module docstring.

    Each line is the record as ERPNext's list API returned it, plus _ingested_at, _source,
    and _batch_id. The file is written as .part and renamed only when complete, and the
    watermark moves only after that. If no record is newer than the watermark (only the
    overlap was re-read), the file is discarded and None is returned. A full load cut
    short by max_records keeps its file but does not set the watermark.
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
            logger.info("No %s records", doctype)
            return None
        logger.info("Full load of %s by name (watermark will be %s)...", doctype, new_watermark)
        records = iter_records_by_name(session, base_url, doctype, fields=fields)
    else:
        new_watermark = watermark
        since = overlap_start(watermark, overlap)
        logger.info("Listing %s modified since %s (watermark %s)...", doctype, since, watermark)
        records = iter_records(session, base_url, doctype, since=since, fields=fields)

    batch_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()
    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{name_slug}_{run_timestamp}_{batch_id[:8]}.jsonl"
    part_path = file_path.with_suffix(".jsonl.part")

    written = 0
    newer = 0
    truncated = False
    with open(part_path, "w", encoding="utf-8") as f:
        for record in records:
            record["_ingested_at"] = ingested_at
            record["_source"] = f"erpnext/{name_slug}"
            record["_batch_id"] = batch_id
            f.write(json.dumps(record) + "\n")

            written += 1
            if watermark is None or record["modified"] > watermark:
                newer += 1
            if watermark is not None:
                new_watermark = max(new_watermark, record["modified"])
            if written % PROGRESS_EVERY == 0:
                logger.info("Extracted %d %s", written, doctype)
            if max_records and written >= max_records:
                truncated = True
                break

    if newer == 0:
        part_path.unlink()
        logger.info("No new or modified %s since %s", doctype, watermark)
        return None

    part_path.replace(file_path)
    if watermark is None and truncated:
        logger.warning("Full load stopped at %d records; watermark not set", written)
    else:
        update_watermark(doctype, new_watermark, written, ingested_at, state_file=watermark_path)
    logger.info(
        "Extracted %d %s (%d newer than the watermark) to %s", written, doctype, newer, file_path
    )
    return file_path
