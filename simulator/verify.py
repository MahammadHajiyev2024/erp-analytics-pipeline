"""Verify simulated days: ERPNext must match what the simulator recalculates.

Usage: uv run python -m simulator.verify 2025-12-06 2026-01-14 --test

The simulator is deterministic, so every simulated day can be recalculated from the
source data and compared with ERPNext, as of the last day: sales and returns, the
cancellations, which invoices are settled or still open, purchases, and successor
products. ERPNext is read as the read-only pipeline user, and the script exits with
status 1 if anything differs. Segment reviews depend on ERPNext's own data at review time
and are not verified.
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import requests

from bootstrap.invoices import PAYMENT_TERMS_DAYS
from bootstrap.load_invoices import prepare
from bootstrap.load_master import load_suppliers
from bootstrap.payments import payment_delay_days
from bootstrap.verify import (
    MAX_PROBLEMS_SHOWN,
    MONEY_COLUMNS,
    TOLERANCE,
    compare,
    expected_purchases,
    expected_sales,
    pipeline_session,
    wrong_customers,
)
from common.erpnext import list_values
from simulator.changes import to_cancel
from simulator.load import (
    PURCHASE_PREFIX,
    Simulation,
    build_simulation,
    days_between,
    load_environment,
    month_days,
)

SALES_FIELDS = [
    "custom_source_invoice",
    "customer",
    "posting_date",
    "docstatus",
    "total_qty",
    *MONEY_COLUMNS,
    "outstanding_amount",
]


def payment_day(invoice: str, customer: str, posted: date) -> date:
    """Return the day an invoice is paid or refunded, by the bootstrap's payment rule."""
    return posted + timedelta(days=payment_delay_days(invoice, customer))


def payment_problems(submitted: pd.DataFrame, as_of: date) -> list[str]:
    """Return the invoices that are open although paid, or settled although not yet due.

    submitted is indexed by source invoice and has customer, posting_date, grand_total,
    and outstanding_amount columns.
    """
    problems = []
    for key, invoice in submitted.iterrows():
        posted = date.fromisoformat(str(invoice["posting_date"]))
        due = payment_day(key, invoice["customer"], posted)
        open_amount = abs(float(invoice["outstanding_amount"]))
        if due <= as_of and open_amount > TOLERANCE:
            problems.append(f"Sales invoice {key} should be settled on {due} but is open")
        if due > as_of and abs(open_amount - abs(float(invoice["grand_total"]))) > TOLERANCE:
            problems.append(f"Sales invoice {key} is not due until {due} but is settled")
    return problems


def set_problems(expected: set[str], actual: set[str], what: str) -> list[str]:
    """Return a description of every key that is expected but missing, or unexpected."""
    problems = [f"{what} missing: {key}" for key in sorted(expected - actual)]
    return problems + [f"{what} not expected: {key}" for key in sorted(actual - expected)]


def verify_sales(
    session: requests.Session, base_url: str, simulation: Simulation, days: list[date]
) -> tuple[list[str], list[str]]:
    """Check sales, returns, cancellations, and payments; return a summary and problems."""
    rows = pd.concat([simulation.day(day) for day in days])
    expected = expected_sales(rows)
    chosen = {key for day in days[:-1] for key in to_cancel(simulation.day(day))}

    filters = [
        ["custom_source_invoice", "like", "SIM-%"],
        ["posting_date", "between", [days[0].isoformat(), days[-1].isoformat()]],
        ["docstatus", "in", [1, 2]],
    ]
    stored = list_values(session, base_url, "Sales Invoice", SALES_FIELDS, filters)
    actual = pd.DataFrame(stored, columns=SALES_FIELDS).set_index("custom_source_invoice")
    submitted = actual[actual["docstatus"] == 1]
    cancelled = set(actual.index[actual["docstatus"] == 2])

    columns = ["total_qty", *MONEY_COLUMNS]
    expected_open = expected.drop(index=list(chosen & set(expected.index)))
    problems = compare(expected_open, submitted, columns, "Sales invoice")
    problems += wrong_customers(expected_open, submitted)
    problems += set_problems(chosen, cancelled, "Cancellation")
    problems += payment_problems(submitted, days[-1])

    open_invoices = submitted[submitted["outstanding_amount"].abs() > TOLERANCE]
    terms = timedelta(days=PAYMENT_TERMS_DAYS)
    overdue = [
        key
        for key, invoice in open_invoices.iterrows()
        if date.fromisoformat(str(invoice["posting_date"])) + terms < days[-1]
    ]
    summary = [
        f"Sales invoices: {len(expected):,} expected, {len(actual):,} in ERPNext",
        f"Cancelled: {len(chosen)} expected, {len(cancelled)} in ERPNext",
        f"Open on {days[-1]}: {len(open_invoices):,} invoices, "
        f"£{open_invoices['outstanding_amount'].sum():,.2f}, {len(overdue)} overdue",
    ]
    return summary, problems


def verify_purchases(
    session: requests.Session, base_url: str, simulation: Simulation, days: list[date]
) -> list[str]:
    """Check each simulated month's purchases per supplier."""
    suppliers = load_suppliers()
    problems = []
    for month_start in sorted({day.replace(day=1) for day in days}):
        month = month_days(month_start, simulation.history_end)
        rows = pd.concat([simulation.day(day) for day in month])
        expected = expected_purchases(rows, simulation.products, suppliers)
        filters = [
            ["docstatus", "=", 1],
            ["bill_no", "like", f"{PURCHASE_PREFIX}{month_start:%Y-%m} %"],
        ]
        fields = ["supplier", "total_qty", "net_total"]
        stored = list_values(session, base_url, "Purchase Invoice", fields, filters)
        actual = pd.DataFrame(stored, columns=fields).set_index("supplier")
        what = f"Purchase {month_start:%Y-%m}"
        problems += compare(expected, actual, ["total_qty", "net_total"], what)
    return problems


def verify_products(
    session: requests.Session, base_url: str, simulation: Simulation, last_day: date
) -> list[str]:
    """Check that launched successors are enabled and their originals disabled."""
    launched = simulation.launched(last_day.replace(day=1))
    codes = [*launched, *launched.values()]
    if not codes:
        return []
    rows = list_values(session, base_url, "Item", ["name", "disabled"], [["name", "in", codes]])
    disabled = {row["name"]: row["disabled"] for row in rows}
    problems = [f"Item missing: {code}" for code in codes if code not in disabled]
    problems += [f"Original still enabled: {code}" for code in launched if disabled.get(code) == 0]
    return problems + [
        f"Successor disabled: {new}" for new in launched.values() if disabled.get(new) == 1
    ]


def verify_days(
    session: requests.Session, base_url: str, simulation: Simulation, days: list[date]
) -> tuple[list[str], list[str]]:
    """Check a range of simulated days in every way; return a summary and the problems."""
    summary, problems = verify_sales(session, base_url, simulation, days)
    problems += verify_purchases(session, base_url, simulation, days)
    problems += verify_products(session, base_url, simulation, days[-1])
    return summary, problems


def main() -> None:
    """Verify a range of simulated days and exit with status 1 if anything differs."""
    parser = argparse.ArgumentParser(description="Verify simulated days against ERPNext.")
    parser.add_argument("first", help="the first simulated day, as YYYY-MM-DD")
    parser.add_argument("last", help="the last simulated day, as YYYY-MM-DD")
    parser.add_argument("--test", action="store_true", help="use the test ERPNext")
    arguments = parser.parse_args()
    first = datetime.strptime(arguments.first, "%Y-%m-%d").date()
    last = datetime.strptime(arguments.last, "%Y-%m-%d").date()

    load_environment(arguments.test)
    base_url = os.environ["ERPNEXT_URL"]
    session = pipeline_session()
    cleaned, products = prepare()
    simulation = build_simulation(cleaned, products, last)
    days = days_between(first, last)

    summary, problems = verify_days(session, base_url, simulation, days)

    print(f"Verifying {first} to {last} in {base_url}")
    print("\n".join(summary))
    if problems:
        print(f"{len(problems):,} problems found:")
        for problem in problems[:MAX_PROBLEMS_SHOWN]:
            print(f"  {problem}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
