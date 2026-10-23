"""Load one month of invoices into ERPNext: purchases, then sales and returns, then payments.

Usage: uv run python -m bootstrap.load_invoices 2025-11

Each step only creates what is missing, so the load can be run again at any time, and
after an interruption it continues where it stopped (docs/bootstrap-rules.md).
"""

import argparse
import logging
import os
from datetime import date, datetime

import pandas as pd
from dotenv import load_dotenv

from bootstrap.clean import clean
from bootstrap.invoices import in_month, purchase_invoice_docs, sales_invoice_docs
from bootstrap.load_master import load_suppliers
from bootstrap.payments import payment_docs
from bootstrap.products import build_products, load_categories
from bootstrap.source import load_source
from common.erpnext import create_missing, get_session, list_values

INVOICE_FIELDS = [
    "name",
    "custom_source_invoice",
    "customer",
    "posting_date",
    "grand_total",
    "is_return",
]

logger = logging.getLogger(__name__)


def purchase_date(month_start: date, history_start: date) -> date:
    """Return the day the month's purchases are made: its first day, or the history's."""
    return max(month_start, history_start)


def chronological(docs: list[dict]) -> list[dict]:
    """Return documents ordered by posting date and time, the order ERPNext values stock in."""
    return sorted(docs, key=lambda doc: (doc["posting_date"], doc["posting_time"]))


def month_filters(month_start: date) -> list[list]:
    """Return ERPNext filters for submitted bootstrap sales invoices posted in the month."""
    month_end = (pd.Timestamp(month_start) + pd.offsets.MonthEnd(0)).date()
    return [
        ["docstatus", "=", 1],
        ["custom_source_invoice", "is", "set"],
        ["posting_date", "between", [month_start.isoformat(), month_end.isoformat()]],
    ]


def main() -> None:
    """Load one month's purchases, sales and returns, and payments as the bootstrap user."""
    parser = argparse.ArgumentParser(description="Load one month of invoices into ERPNext.")
    parser.add_argument("month", help="the month to load, as YYYY-MM, such as 2025-11")
    month_start = datetime.strptime(parser.parse_args().month, "%Y-%m").date()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    load_dotenv()
    base_url = os.environ["ERPNEXT_URL"]
    session = get_session(
        os.environ["ERPNEXT_BOOTSTRAP_API_KEY"], os.environ["ERPNEXT_BOOTSTRAP_API_SECRET"]
    )

    cleaned, _ = clean(load_source())
    categories, other_cost_ratio = load_categories()
    products = build_products(cleaned, categories, other_cost_ratio).set_index("stock_code")
    rows = in_month(cleaned, month_start.year, month_start.month)
    if rows.empty:
        logger.info("No source data in %s", f"{month_start:%Y-%m}")
        return

    history_start = cleaned["invoice_date"].min().date()
    bought_on = purchase_date(month_start, history_start)
    purchases = purchase_invoice_docs(rows, products, load_suppliers(), bought_on)
    create_missing(session, base_url, "Purchase Invoice", purchases, "bill_no")

    sales = chronological(sales_invoice_docs(rows, products))
    create_missing(session, base_url, "Sales Invoice", sales, "custom_source_invoice")

    stored = list_values(
        session, base_url, "Sales Invoice", INVOICE_FIELDS, month_filters(month_start)
    )
    payments = payment_docs(pd.DataFrame(stored))
    create_missing(session, base_url, "Payment Entry", payments, "reference_no")


if __name__ == "__main__":
    main()
