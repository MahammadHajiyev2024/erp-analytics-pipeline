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

from bootstrap.customers import build_customers
from bootstrap.invoices import purchase_invoice_docs, sales_invoice_docs
from bootstrap.load_invoices import INVOICE_FIELDS, bootstrap_session, chronological, prepare
from bootstrap.load_master import customer_docs, item_docs, load_suppliers
from bootstrap.payments import MAX_DELAY_DAYS, payment_docs
from bootstrap.products import load_categories
from common.erpnext import cancel, create_missing, list_values, update
from simulator.changes import reviewed_segments, segment_changes, to_cancel
from simulator.days import first_orders, simulate_day
from simulator.successors import apply_successors, successor_products, successors

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


def new_customer_docs(rows: pd.DataFrame, customers: pd.DataFrame) -> list[dict]:
    """Return a Customer for each new customer in the rows, with its original's segment.

    customers must be indexed by customer ID; new customer IDs end with the original's ID.
    """
    new = rows[rows["customer"].str.startswith("SIM-")].drop_duplicates("customer")
    if new.empty:
        return []
    originals = new["customer"].str.split("-").str[-1]
    profiles = pd.DataFrame(
        {
            "customer": new["customer"].to_numpy(),
            "country": new["country"].to_numpy(),
            "segment": customers.loc[originals, "segment"].to_numpy(),
        }
    )
    return customer_docs(profiles)


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


def enabled_items(session: requests.Session, base_url: str, codes: list[str]) -> list[str]:
    """Return which of the given items are still enabled in ERPNext."""
    if not codes:
        return []
    filters = [["name", "in", codes], ["disabled", "=", 0]]
    return sorted(row["name"] for row in list_values(session, base_url, "Item", ["name"], filters))


def review_segments(session: requests.Session, base_url: str, review_day: date) -> None:
    """Update the segment of every customer whose last 12 months of orders call for it."""
    window = [
        (review_day - timedelta(days=365)).isoformat(),
        (review_day - timedelta(days=1)).isoformat(),
    ]
    filters = [["docstatus", "=", 1], ["is_return", "=", 0], ["posting_date", "between", window]]
    orders = list_values(session, base_url, "Sales Invoice", ["customer", "net_total"], filters)
    groups = list_values(session, base_url, "Customer", ["name", "customer_group"])
    current = {row["name"]: row["customer_group"] for row in groups}
    reviewed = reviewed_segments(pd.DataFrame(orders, columns=["customer", "net_total"]))
    changes = segment_changes(current, reviewed)
    for customer, group in sorted(changes.items()):
        update(session, base_url, "Customer", customer, {"customer_group": group})
    logger.info("Segment review on %s: %d customers changed", review_day, len(changes))


def cancel_invoices(session: requests.Session, base_url: str, keys: list[str]) -> None:
    """Cancel the invoices with the given source keys that are still submitted."""
    if not keys:
        return
    filters = [["docstatus", "=", 1], ["custom_source_invoice", "in", keys]]
    for row in list_values(session, base_url, "Sales Invoice", ["name"], filters):
        cancel(session, base_url, "Sales Invoice", row["name"])
        logger.info("Sales Invoice %s cancelled", row["name"])


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
    """Load each month's products, segment review, and purchases, then each day's activity.

    A day's activity is its sales and returns, the cancellations of the previous day's
    chosen invoices, and the payments that fall due.
    """
    history_end = cleaned["invoice_date"].max().date()
    suppliers = load_suppliers()
    customers = build_customers(cleaned).set_index("customer")
    new_customer_invoices = first_orders(cleaned)
    months = sorted({day.replace(day=1) for day in days})

    replaced = successors(cleaned, products, history_end, months[-1])
    new_products = successor_products(products, replaced, *load_categories())
    all_products = pd.concat([products, new_products])

    def simulate(day: date) -> pd.DataFrame:
        rows = simulate_day(cleaned, day, history_end, new_customer_invoices)
        return apply_successors(rows, replaced, day)

    for month_start in months:
        month = month_days(month_start, history_end)
        logger.info("=== %s: products and purchases ===", f"{month_start:%Y-%m}")
        launched = {code: new for code, (new, launch) in replaced.items() if launch <= month_start}
        launched_products = new_products.loc[list(launched.values())].reset_index()
        create_missing(
            session, base_url, "Item", item_docs(launched_products, suppliers), "item_code"
        )
        for code in enabled_items(session, base_url, list(launched)):
            update(session, base_url, "Item", code, {"disabled": 1})
            logger.info("Item %s disabled, replaced by %s", code, launched[code])

        review_segments(session, base_url, month[0])

        rows = pd.concat([simulate(day) for day in month])
        purchases = purchase_invoice_docs(
            rows, all_products, suppliers, month[0], bill_prefix=PURCHASE_PREFIX
        )
        create_missing(session, base_url, "Purchase Invoice", purchases, "bill_no")

        for day in [day for day in days if day.replace(day=1) == month_start]:
            logger.info("=== %s: sales ===", day)
            rows = simulate(day)
            create_missing(
                session, base_url, "Customer", new_customer_docs(rows, customers), "customer_name"
            )
            sales = sales_invoice_docs(rows, all_products)
            create_missing(
                session, base_url, "Sales Invoice", chronological(sales), "custom_source_invoice"
            )
            previous = day - timedelta(days=1)
            if previous > history_end:
                cancel_invoices(session, base_url, to_cancel(simulate(previous)))
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
