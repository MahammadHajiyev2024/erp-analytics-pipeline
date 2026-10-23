"""Verify one loaded month: ERPNext must match the clean source data, invoice by invoice.

Usage: uv run python -m bootstrap.verify 2025-11

ERPNext is read as the read-only pipeline user, so verifying can never change the data it
checks. The script exits with status 1 if anything differs, so a pipeline can stop on it.
"""

import argparse
import os
import sys
from datetime import date

import pandas as pd
import requests
from dotenv import load_dotenv

from bootstrap.invoices import UK, UK_VAT_RATE, in_month, purchase_quantities
from bootstrap.load_invoices import month_filters, parse_month, prepare
from bootstrap.load_master import load_suppliers
from common.erpnext import get_session, list_values

TOLERANCE = 0.01  # Largest accepted difference per invoice, in GBP or units
MONEY_COLUMNS = ["net_total", "total_taxes_and_charges", "grand_total"]
SALES_FIELDS = [
    "custom_source_invoice",
    "customer",
    "total_qty",
    *MONEY_COLUMNS,
    "outstanding_amount",
]
PURCHASE_FIELDS = ["supplier", "total_qty", "net_total"]
MAX_PROBLEMS_SHOWN = 20


def expected_sales(rows: pd.DataFrame) -> pd.DataFrame:
    """Return what each sales invoice should total, indexed by source invoice number.

    Each line is rounded to pennies before the lines are added up, as ERPNext does.
    """
    lines = rows.assign(amount=(rows["quantity"] * rows["price"]).round(2))
    invoices = lines.groupby("invoice").agg(
        customer=("customer", "first"),
        country=("country", "first"),
        total_qty=("quantity", "sum"),
        net_total=("amount", "sum"),
    )
    vat_rate = invoices["country"].eq(UK).astype(float) * UK_VAT_RATE / 100
    invoices["total_taxes_and_charges"] = (invoices["net_total"] * vat_rate).round(2)
    invoices["grand_total"] = invoices["net_total"] + invoices["total_taxes_and_charges"]
    return invoices.drop(columns="country")


def expected_purchases(
    rows: pd.DataFrame, products: pd.DataFrame, suppliers: dict[str, str]
) -> pd.DataFrame:
    """Return each supplier's expected purchase quantity and value, indexed by supplier.

    products must be indexed by stock code.
    """
    quantities = purchase_quantities(rows, products)
    costs = products.loc[quantities.index, "cost"]
    lines = pd.DataFrame(
        {
            "supplier": [suppliers[products.at[code, "category"]] for code in quantities.index],
            "total_qty": quantities.to_numpy(),
            "net_total": (quantities * costs).round(2).to_numpy(),
        }
    )
    return lines.groupby("supplier")[["total_qty", "net_total"]].sum()


def compare(
    expected: pd.DataFrame, actual: pd.DataFrame, columns: list[str], what: str
) -> list[str]:
    """Return a description of every difference between expected and stored documents.

    Both frames must be indexed by the same key, such as the source invoice number.
    """
    missing = expected.index.difference(actual.index)
    unexpected = actual.index.difference(expected.index)
    problems = [f"{what} missing from ERPNext: {key}" for key in missing]
    problems += [f"{what} not in the source data: {key}" for key in unexpected]
    both = expected.index.intersection(actual.index)
    for column in columns:
        difference = (expected.loc[both, column] - actual.loc[both, column]).abs()
        for key in both[(difference > TOLERANCE + 1e-9).to_numpy()]:
            problems.append(
                f"{what} {key} {column}: expected {expected.at[key, column]}, "
                f"ERPNext {actual.at[key, column]}"
            )
    return problems


def wrong_customers(expected: pd.DataFrame, actual: pd.DataFrame) -> list[str]:
    """Return the invoices stored with a different customer than in the source data."""
    both = expected.index.intersection(actual.index)
    differs = expected.loc[both, "customer"] != actual.loc[both, "customer"]
    return [f"Sales invoice {key} has the wrong customer" for key in both[differs.to_numpy()]]


def unsettled(actual: pd.DataFrame) -> list[str]:
    """Return the invoices and returns that still have an outstanding amount."""
    open_amounts = actual["outstanding_amount"].abs() > 1e-9
    open_keys = actual.index[open_amounts.to_numpy()]
    return [f"Sales invoice {key} is not settled" for key in open_keys]


def verify_month(
    session: requests.Session,
    base_url: str,
    cleaned: pd.DataFrame,
    products: pd.DataFrame,
    month_start: date,
) -> tuple[list[str], list[str]]:
    """Compare one month in ERPNext with the source; return a summary and the problems."""
    rows = in_month(cleaned, month_start.year, month_start.month)
    expected = expected_sales(rows)
    stored = list_values(
        session, base_url, "Sales Invoice", SALES_FIELDS, month_filters(month_start)
    )
    actual = pd.DataFrame(stored, columns=SALES_FIELDS).set_index("custom_source_invoice")

    purchase_filters = [["docstatus", "=", 1], ["bill_no", "like", f"{month_start:%Y-%m} %"]]
    expected_bought = expected_purchases(rows, products, load_suppliers())
    bought = list_values(session, base_url, "Purchase Invoice", PURCHASE_FIELDS, purchase_filters)
    actual_bought = pd.DataFrame(bought, columns=PURCHASE_FIELDS).set_index("supplier")

    problems = compare(expected, actual, ["total_qty", *MONEY_COLUMNS], "Sales invoice")
    problems += wrong_customers(expected, actual)
    problems += unsettled(actual)
    problems += compare(expected_bought, actual_bought, ["total_qty", "net_total"], "Purchase")

    summary = [f"Sales invoices: {len(expected):,} expected, {len(actual):,} in ERPNext"]
    for column, label in [("net_total", "Net sales"), ("total_taxes_and_charges", "VAT")]:
        summary.append(
            f"{label}: £{expected[column].sum():,.2f} expected, "
            f"£{actual[column].sum():,.2f} in ERPNext"
        )
    summary.append(f"Purchases: {len(expected_bought)} expected, {len(actual_bought)} in ERPNext")
    return summary, problems


def pipeline_session() -> requests.Session:
    """Return a session for the read-only pipeline user."""
    return get_session(os.environ["ERPNEXT_API_KEY"], os.environ["ERPNEXT_API_SECRET"])


def main() -> None:
    """Verify one month and exit with status 1 if anything differs."""
    parser = argparse.ArgumentParser(description="Verify one loaded month against the source.")
    parser.add_argument("month", help="the month to verify, as YYYY-MM, such as 2025-11")
    month_start = parse_month(parser.parse_args().month)

    load_dotenv()
    cleaned, products = prepare()
    summary, problems = verify_month(
        pipeline_session(), os.environ["ERPNEXT_URL"], cleaned, products, month_start
    )
    print("\n".join(summary))
    if problems:
        print(f"{len(problems):,} problems found:")
        for problem in problems[:MAX_PROBLEMS_SHOWN]:
            print(f"  {problem}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
