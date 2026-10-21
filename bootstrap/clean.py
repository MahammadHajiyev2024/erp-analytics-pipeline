"""Cleaning rules for the source data, as described in docs/bootstrap-rules.md."""

from collections.abc import Callable

import pandas as pd

from bootstrap.source import load_source

INTERNAL_CODES = ["M", "BANK CHARGES", "TEST001", "TEST002"]
DISCOUNT_CODE = "D"
GUEST_CUSTOMER = "Guest Customer"
DATE_SHIFT = pd.Timedelta(weeks=730)  # Design decision 14


def is_cancellation(df: pd.DataFrame) -> pd.Series:
    """Return True for rows on cancellation invoices (invoice numbers starting with C)."""
    return df["invoice"].str.startswith("C")


def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove rows that are exact copies of an earlier row."""
    return df.drop_duplicates()


def exclude_internal_codes(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude manual adjustments, bank charges, and test items."""
    return df[~df["stock_code"].isin(INTERNAL_CODES)]


def exclude_invalid_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude rows with a zero or negative price."""
    return df[df["price"] > 0]


def exclude_adjustments(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude negative quantities that are not on cancellation invoices."""
    return df[~((df["quantity"] < 0) & ~is_cancellation(df))]


def exclude_misplaced_discounts(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude discount lines on normal invoices, which are data errors."""
    return df[~((df["stock_code"] == DISCOUNT_CODE) & ~is_cancellation(df))]


def add_customer(df: pd.DataFrame) -> pd.DataFrame:
    """Add the customer each row belongs to; rows without an ID go to the Guest Customer."""
    customer = df["customer_id"].astype("string").fillna(GUEST_CUSTOMER)
    return df.assign(customer=customer)


def shift_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Move invoice dates forward by 730 weeks, keeping each order on its weekday."""
    return df.assign(invoice_date=df["invoice_date"] + DATE_SHIFT)


RULES: list[Callable[[pd.DataFrame], pd.DataFrame]] = [
    remove_duplicates,
    exclude_internal_codes,
    exclude_invalid_prices,
    exclude_adjustments,
    exclude_misplaced_discounts,
]


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply the cleaning rules in order, then add customers and shift dates.

    Returns the result and the number of rows each rule removed.
    """
    removed = {}
    for rule in RULES:
        before = len(df)
        df = rule(df)
        removed[rule.__name__] = before - len(df)
    return shift_dates(add_customer(df)).reset_index(drop=True), removed


def main() -> None:
    """Clean the source data and report what each rule removed."""
    df = load_source()
    print(f"Source rows: {len(df):,}")

    cleaned, removed = clean(df)
    for rule, count in removed.items():
        print(f"  {rule}: -{count:,}")

    print(f"Clean rows: {len(cleaned):,}")
    print(f"  Cancellation rows: {is_cancellation(cleaned).sum():,}")
    print(f"  Guest Customer rows: {(cleaned['customer'] == GUEST_CUSTOMER).sum():,}")
    print(f"  Invoices: {cleaned['invoice'].nunique():,}")
    print(f"  Dates: {cleaned['invoice_date'].min()} to {cleaned['invoice_date'].max()}")


if __name__ == "__main__":
    main()
