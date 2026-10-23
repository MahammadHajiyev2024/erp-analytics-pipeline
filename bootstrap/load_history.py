"""Load and verify a range of months in order, stopping at the first month that fails.

Usage: uv run python -m bootstrap.load_history 2023-11 2024-04

The source data is cleaned once. Each month is loaded as the bootstrap user, then verified
as the read-only pipeline user. Like the monthly load, it can be run again at any time and
continues where it stopped.
"""

import argparse
import logging
import os
import sys
from datetime import date

import pandas as pd
from dotenv import load_dotenv

from bootstrap.load_invoices import bootstrap_session, load_month, parse_month, prepare
from bootstrap.verify import MAX_PROBLEMS_SHOWN, pipeline_session, verify_month

logger = logging.getLogger(__name__)


def months(first: date, last: date) -> list[date]:
    """Return the first day of every month from first to last, both included."""
    return [day.date() for day in pd.date_range(first, last, freq="MS")]


def main() -> None:
    """Load and verify every month in the given range, in order."""
    parser = argparse.ArgumentParser(description="Load and verify a range of months.")
    parser.add_argument("first", help="the first month to load, as YYYY-MM")
    parser.add_argument("last", help="the last month to load, as YYYY-MM")
    arguments = parser.parse_args()
    selected = months(parse_month(arguments.first), parse_month(arguments.last))

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    load_dotenv()
    base_url = os.environ["ERPNEXT_URL"]
    writer, reader = bootstrap_session(), pipeline_session()
    cleaned, products = prepare()

    for month_start in selected:
        label = f"{month_start:%Y-%m}"
        logger.info("=== %s: loading ===", label)
        load_month(writer, base_url, cleaned, products, month_start)
        summary, problems = verify_month(reader, base_url, cleaned, products, month_start)
        for line in summary:
            logger.info("%s %s", label, line)
        if problems:
            logger.error("%s: %d problems found, stopping", label, len(problems))
            for problem in problems[:MAX_PROBLEMS_SHOWN]:
                logger.error("  %s", problem)
            sys.exit(1)
        logger.info("=== %s: all checks passed ===", label)

    logger.info("Loaded and verified %d months", len(selected))


if __name__ == "__main__":
    main()
