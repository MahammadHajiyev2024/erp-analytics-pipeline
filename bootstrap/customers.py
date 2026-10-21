"""Build the customer list: one row per customer, with its country and segment.

The rules are described in docs/bootstrap-rules.md.
"""

import pandas as pd

from bootstrap.clean import GUEST_CUSTOMER, clean, is_cancellation
from bootstrap.source import load_source

WHOLESALE_THRESHOLD = 150.0  # Typical order value in GBP from which a customer is Wholesale
WHOLESALE = "Wholesale"
RETAIL = "Retail"
GUEST = "Guest"


def typical_order_values(df: pd.DataFrame) -> pd.Series:
    """Return each customer's median order value, counting sales invoices only."""
    sales = df[~is_cancellation(df)]
    values = sales.assign(value=sales["quantity"] * sales["price"])
    orders = values.groupby(["customer", "invoice"])["value"].sum()
    return orders.groupby("customer").median()


def segment(customer: str, typical_order_value: float) -> str:
    """Return a customer's segment; customers without any sale count as Retail."""
    if customer == GUEST_CUSTOMER:
        return GUEST
    if pd.notna(typical_order_value) and typical_order_value >= WHOLESALE_THRESHOLD:
        return WHOLESALE
    return RETAIL


def countries(df: pd.DataFrame) -> pd.Series:
    """Return each customer's most frequent invoice country."""
    return df.groupby("customer")["country"].agg(lambda names: names.mode().iloc[0])


def build_customers(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per customer with country, typical order value, and segment."""
    country = countries(df)
    typical = typical_order_values(df).reindex(country.index)
    customers = pd.DataFrame(
        {
            "customer": country.index,
            "country": country.to_numpy(),
            "typical_order_value": typical.to_numpy(),
        }
    )
    pairs = zip(customers["customer"], customers["typical_order_value"], strict=True)
    customers["segment"] = [segment(customer, value) for customer, value in pairs]
    return customers


def main() -> None:
    """Build the customer list and report the segments."""
    cleaned, _ = clean(load_source())
    customers = build_customers(cleaned)

    print(f"Customers: {len(customers):,} in {customers['country'].nunique()} countries")
    for name, count in customers["segment"].value_counts().items():
        print(f"  {name}: {count:,}")
    without_sales = customers["typical_order_value"].isna().sum()
    print(f"Customers without any sale (counted as Retail): {without_sales:,}")


if __name__ == "__main__":
    main()
