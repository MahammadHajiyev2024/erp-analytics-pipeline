import pandas as pd

from bootstrap.clean import GUEST_CUSTOMER
from simulator.changes import reviewed_segments, segment_changes, to_cancel


def test_to_cancel_picks_about_half_a_percent_of_sales():
    rows = pd.DataFrame(
        {"invoice": [f"SIM-20260107-1-{number}" for number in range(40000)], "customer": "17850"}
    )

    share = len(to_cancel(rows)) / len(rows)

    assert 0.004 < share < 0.006


def test_to_cancel_never_picks_returns_or_guest_orders():
    keys = [f"SIM-20260107-1-{number}" for number in range(2000)]
    returns = pd.DataFrame({"invoice": [f"SIM-20260107-1-C{n}" for n in range(2000)]})
    guests = pd.DataFrame({"invoice": keys, "customer": GUEST_CUSTOMER})

    assert to_cancel(returns.assign(customer="17850")) == []
    assert to_cancel(guests) == []


def test_reviewed_segments_use_the_median_order():
    orders = pd.DataFrame(
        {"customer": ["A", "A", "A", "B"], "net_total": [100.0, 200.0, 300.0, 149.99]}
    )

    assert reviewed_segments(orders) == {"A": "Wholesale", "B": "Retail"}


def test_segment_changes_only_report_known_customers_whose_segment_differs():
    current = {"A": "Retail", "B": "Retail", GUEST_CUSTOMER: "Guest"}
    reviewed = {"A": "Wholesale", "B": "Retail", "C": "Wholesale", GUEST_CUSTOMER: "Guest"}

    assert segment_changes(current, reviewed) == {"A": "Wholesale"}
