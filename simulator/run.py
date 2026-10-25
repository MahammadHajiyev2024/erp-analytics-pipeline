"""Simulate every missing day up to yesterday, then verify the last 60 days.

Usage: uv run python -m simulator.run [--test] [--until YYYY-MM-DD]

This is the daily command: the first run catches up from the end of the history, and
every later run simulates only the days since the last one. The start is found in
ERPNext itself, from the latest simulated invoice. The run exits with status 1 if the
verification fails.
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta

from bootstrap.load_invoices import bootstrap_session, prepare
from bootstrap.verify import MAX_PROBLEMS_SHOWN, pipeline_session
from common.erpnext import list_values
from simulator.load import build_simulation, days_between, load_days, load_environment
from simulator.verify import verify_days

# Payments arrive up to 50 days after an invoice, so a run can change any invoice of the
# last 50 days; 60 days covers them with some margin.
VERIFY_WINDOW_DAYS = 60

logger = logging.getLogger(__name__)


def next_day(keys: list[str], history_end: date) -> date:
    """Return the first day to simulate: the day after the latest simulated invoice."""
    days = [datetime.strptime(key.split("-")[1], "%Y%m%d").date() for key in keys]
    return max(days, default=history_end) + timedelta(days=1)


def verification_window(until: date, history_end: date) -> list[date]:
    """Return the simulated days of the last VERIFY_WINDOW_DAYS days up to until."""
    first = max(history_end + timedelta(days=1), until - timedelta(days=VERIFY_WINDOW_DAYS - 1))
    return days_between(first, until)


def main() -> None:
    """Simulate the missing days and verify the recent ones."""
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Simulate every missing day, then verify.")
    parser.add_argument("--test", action="store_true", help="use the test ERPNext")
    parser.add_argument(
        "--until", default=yesterday.isoformat(), help="the last day to simulate (YYYY-MM-DD)"
    )
    arguments = parser.parse_args()
    until = datetime.strptime(arguments.until, "%Y-%m-%d").date()
    if until > yesterday:
        parser.error("only complete days can be simulated: --until must be before today")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    load_environment(arguments.test)
    base_url = os.environ["ERPNEXT_URL"]
    reader = pipeline_session()
    cleaned, products = prepare()
    history_end = cleaned["invoice_date"].max().date()

    filters = [["custom_source_invoice", "like", "SIM-%"]]
    rows = list_values(reader, base_url, "Sales Invoice", ["custom_source_invoice"], filters)
    first = next_day([row["custom_source_invoice"] for row in rows], history_end)
    simulation = build_simulation(cleaned, products, until)

    if first <= until:
        logger.info("Simulating %s to %s in %s", first, until, base_url)
        load_days(bootstrap_session(), base_url, simulation, days_between(first, until))
    else:
        logger.info("Nothing to simulate: %s is already simulated", until)

    window = verification_window(until, history_end)
    summary, problems = verify_days(reader, base_url, simulation, window)
    logger.info("Verified %s to %s", window[0], window[-1])
    for line in summary:
        logger.info(line)
    if problems:
        logger.error("%d problems found", len(problems))
        for problem in problems[:MAX_PROBLEMS_SHOWN]:
            logger.error("  %s", problem)
        sys.exit(1)
    logger.info("All checks passed")


if __name__ == "__main__":
    main()
