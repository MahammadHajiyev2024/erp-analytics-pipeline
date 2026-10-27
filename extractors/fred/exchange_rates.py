"""Extract daily GBP-to-USD exchange rates (FRED series DEXUSUK) to the landing folder.

DEXUSUK is US dollars per one pound sterling: the Federal Reserve's H.10 noon buying
rate in New York. FRED publishes it weekly, and US holidays have the value "." (kept as
received; silver and gold handle it). Each run re-reads OVERLAP before the watermark
(the latest observation date), to catch late or revised values; silver keeps the latest
version of each date.

The API key travels in the URL, so error messages and urllib3's retry warnings are
redacted before they are raised or logged.
"""

import argparse
import json
import logging
import os
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

from common.erpnext import READ_RETRY
from extractors.watermark import DEFAULT_STATE_FILE, get_watermark, update_watermark

logger = logging.getLogger(__name__)
OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES_ID = "DEXUSUK"
START_DATE = date(2023, 11, 1)  # a few weeks before the history starts (2023-11-28)
OVERLAP = timedelta(days=30)
TIMEOUT_SECONDS = 30
SLUG = "fred_exchange_rates"


class FREDError(Exception):
    """A FRED request failed."""


def redact(text: str) -> str:
    """Replace the value of any api_key parameter in text with ***."""
    return re.sub(r"api_key=[^&\s'\"]+", "api_key=***", text)


class RedactApiKey(logging.Filter):
    """Logging filter that removes API keys from log messages (urllib3 logs URLs)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def get_session() -> requests.Session:
    """Return a session that retries GET requests like the ERPNext reads do."""
    logging.getLogger("urllib3.connectionpool").addFilter(RedactApiKey())
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=READ_RETRY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def watermark_key(series_id: str) -> str:
    """Return the key of the series in the watermark file ("FRED DEXUSUK")."""
    return f"FRED {series_id}"


def start_date(watermark: str | None, overlap: timedelta = OVERLAP) -> date:
    """Return the first observation date to request: the watermark minus the overlap."""
    if watermark is None:
        return START_DATE
    return date.fromisoformat(watermark) - overlap


def fetch_observations(
    session: requests.Session, api_key: str, series_id: str, start: date
) -> list[dict[str, Any]]:
    """Return all observations of the series from the start date, oldest first."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.isoformat(),
        "sort_order": "asc",
    }
    try:
        response = session.get(OBSERVATIONS_URL, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as error:
        # from None: the original exception's message contains the URL with the key
        raise FREDError(redact(f"Fetching {series_id} failed: {error}")) from None
    if not response.ok:
        detail = redact(response.text[:300])
        raise FREDError(f"Fetching {series_id} failed: HTTP {response.status_code}: {detail}")

    body = response.json()
    observations = body.get("observations", [])
    if body.get("count", 0) > len(observations):
        raise FREDError(
            f"{series_id}: {body['count']} observations but only {len(observations)} "
            "returned; paging is needed"
        )
    return observations


def extract_exchange_rates(
    series_id: str = SERIES_ID,
    output_dir: Path | None = None,
    watermark_path: Path = DEFAULT_STATE_FILE,
) -> Path | None:
    """Extract observations since the watermark (minus the overlap) to one JSON Lines file.

    Each line is one observation as FRED returned it (realtime_start, realtime_end,
    date, value), plus series_id, _ingested_at, _source, and _batch_id. The file is
    written as .part and renamed when complete; the watermark moves only after that.
    If no observation is newer than the watermark, nothing is written and None is
    returned.
    """
    load_dotenv()
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise ValueError("Missing FRED_API_KEY in environment")

    key = watermark_key(series_id)
    watermark = get_watermark(key, state_file=watermark_path)
    start = start_date(watermark)
    logger.info("Fetching %s from %s (watermark %s)...", series_id, start, watermark)
    observations = fetch_observations(get_session(), api_key, series_id, start)

    newer = [o for o in observations if watermark is None or o["date"] > watermark]
    if not newer:
        logger.info("No %s observations after %s", series_id, watermark)
        return None

    batch_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC).isoformat()
    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = output_dir or Path("data/landing") / SLUG
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{SLUG}_{run_timestamp}_{batch_id[:8]}.jsonl"
    part_path = file_path.with_suffix(".jsonl.part")

    with open(part_path, "w", encoding="utf-8") as f:
        for observation in observations:
            record = {
                **observation,
                "series_id": series_id,
                "_ingested_at": ingested_at,
                "_source": f"fred/{series_id.lower()}",
                "_batch_id": batch_id,
            }
            f.write(json.dumps(record) + "\n")

    part_path.replace(file_path)
    latest = max(o["date"] for o in observations)
    update_watermark(key, latest, len(observations), ingested_at, state_file=watermark_path)
    logger.info(
        "Extracted %d %s observations (%d after the watermark, latest %s) to %s",
        len(observations),
        series_id,
        len(newer),
        latest,
        file_path,
    )
    return file_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract FRED GBP-to-USD exchange rates")
    parser.add_argument("--output-dir", type=Path, help=f"default: data/landing/{SLUG}")
    parser.add_argument("--watermark-path", type=Path, default=DEFAULT_STATE_FILE)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(extract_exchange_rates(output_dir=args.output_dir, watermark_path=args.watermark_path))


if __name__ == "__main__":
    main()
