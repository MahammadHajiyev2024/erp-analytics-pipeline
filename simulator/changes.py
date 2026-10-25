"""Changes to existing records in the simulated period: segment reviews and cancellations.

The rules are described in docs/simulator-rules.md.
"""

import pandas as pd

from bootstrap.clean import GUEST_CUSTOMER, is_cancellation
from bootstrap.customers import segment
from simulator.days import stable_fraction

CANCEL_SHARE = 0.005


def to_cancel(rows: pd.DataFrame) -> list[str]:
    """Return the keys of the day's invoices that are cancelled the next day.

    About 0.5% of sales invoices are chosen by hash; returns and Guest Customer orders,
    which are paid on the day, are never cancelled.
    """
    sales = rows[~is_cancellation(rows) & (rows["customer"] != GUEST_CUSTOMER)]
    keys = sorted(set(sales["invoice"]))
    return [key for key in keys if stable_fraction(key, "cancel") < CANCEL_SHARE]


def reviewed_segments(orders: pd.DataFrame) -> dict[str, str]:
    """Return each customer's segment from their orders' median net total.

    orders has a customer and a net_total column, one row per submitted sales invoice.
    """
    medians = orders.groupby("customer")["net_total"].median()
    return {customer: segment(customer, value) for customer, value in medians.items()}


def segment_changes(current: dict[str, str], reviewed: dict[str, str]) -> dict[str, str]:
    """Return the customers whose reviewed segment differs from their current one."""
    return {
        customer: new
        for customer, new in reviewed.items()
        if customer != GUEST_CUSTOMER and customer in current and current[customer] != new
    }
