"""Load simulated days into ERPNext: each month's purchases, then each day's sales and payments.

Usage: uv run python -m simulator.load 2025-12-06 2025-12-10 --test

With --test, the settings in .env.test are applied on top of .env, so the simulator
talks to the test ERPNext. Like the bootstrap, each step only creates what is missing.
"""

import argparse
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from bootstrap.invoices import purchase_invoice_docs, sales_invoice_docs
from bootstrap.load_invoices import INVOICE_FIELDS, bootstrap_session, chronological, prepare
from bootstrap.load_master import load_suppliers
from bootstrap.payments import MAX_DELAY_DAYS, payment_docs
from common.erpnext import create_missing, list_values
from simulator.days import simulate_day

ROOT = Path(__file__).resolve().parents[1]
PURCHASE_PREFIX = "SIM "

logger = logging.getLogger(__name__)


def days_between(first: date, last: date) -> list[date]:
    """Return every day from first to last, both included."""
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def month_days(day: date, history_end: date) -> list[date]:
    """Return the days of the day's month that come after the end of the history."""
    month_start = day.replace(day=1)
    month_end = (pd.Timestamp(month_start) + pd.offsets.MonthEnd(0)).date()
    return days_between(max(month_start, history_end + timedelta(days=1)), month_end)


def due_payments(invoices: pd.DataFrame, day: date) -> list[dict]:
    """Return the payments and refunds of the given invoices that are due on or before day."""
    if invoices.empty:
        return []
    return [doc for doc in payment_docs(invoices) if doc["posting_date"] <= day.isoformat()]


def recent_simulated_invoices(session: requests.Session, base_url: str, day: date) -> pd.DataFrame:
    """Return the submitted simulated invoices that could fall due on day."""
    window_start = day - timedelta(days=MAX_DELAY_DAYS)
    filters = [
        ["docstatus", "=", 1],
        ["custom_source_invoice", "like", "SIM-%"],
        ["posting_date", "between", [window_start.isoformat(), day.isoformat()]],
    ]
    rows = list_values(session, base_url, "Sales Invoice", INVOICE_FIELDS, filters)
    return pd.DataFrame(rows, columns=INVOICE_FIELDS)


def load_environment(test: bool) -> None:
    """Load .env, and with test, apply .env.test on top of it."""
    load_dotenv(ROOT / ".env")
    if test:
        load_dotenv(ROOT / ".env.test", override=True)


def load_days(
    session: requests.Session,
    base_url: str,
    cleaned: pd.DataFrame,
    products: pd.DataFrame,
    days: list[date],
) -> None:
    """Load each month's purchases, then each day's sales and returns and due payments."""
    history_end = cleaned["invoice_date"].max().date()
    suppliers = load_suppliers()
    months = sorted({day.replace(day=1) for day in days})

    for month_start in months:
        month = month_days(month_start, history_end)
        logger.info("=== %s: purchases ===", f"{month_start:%Y-%m}")
        rows = pd.concat([simulate_day(cleaned, day, history_end) for day in month])
        purchases = purchase_invoice_docs(
            rows, products, suppliers, month[0], bill_prefix=PURCHASE_PREFIX
        )
        create_missing(session, base_url, "Purchase Invoice", purchases, "bill_no")

        for day in [day for day in days if day.replace(day=1) == month_start]:
            logger.info("=== %s: sales ===", day)
            sales = sales_invoice_docs(simulate_day(cleaned, day, history_end), products)
            create_missing(
                session, base_url, "Sales Invoice", chronological(sales), "custom_source_invoice"
            )
            invoices = recent_simulated_invoices(session, base_url, day)
            payments = due_payments(invoices, day)
            create_missing(session, base_url, "Payment Entry", payments, "reference_no")


def main() -> None:
    """Load the given range of simulated days, never today or later."""
    parser = argparse.ArgumentParser(description="Load simulated days into ERPNext.")
    parser.add_argument("first", help="the first day to simulate, as YYYY-MM-DD")
    parser.add_argument("last", help="the last day to simulate, as YYYY-MM-DD")
    parser.add_argument("--test", action="store_true", help="use the test ERPNext")
    arguments = parser.parse_args()
    first = datetime.strptime(arguments.first, "%Y-%m-%d").date()
    last = datetime.strptime(arguments.last, "%Y-%m-%d").date()
    if last >= date.today():
        parser.error("only complete days can be simulated: the last day must be before today")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    load_environment(arguments.test)
    base_url = os.environ["ERPNEXT_URL"]
    logger.info("Simulating %s to %s in %s", first, last, base_url)
    cleaned, products = prepare()
    load_days(bootstrap_session(), base_url, cleaned, products, days_between(first, last))


if __name__ == "__main__":
    main()
