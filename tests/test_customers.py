import pandas as pd

from bootstrap.clean import GUEST_CUSTOMER
from bootstrap.customers import (
    GUEST,
    RETAIL,
    WHOLESALE,
    build_customers,
    segment,
    typical_order_values,
)


def make_rows(*rows: dict) -> pd.DataFrame:
    defaults = {
        "invoice": "536365",
        "customer": "17850",
        "quantity": 1,
        "price": 100.0,
        "country": "United Kingdom",
    }
    df = pd.DataFrame([defaults | row for row in rows])
    df["invoice"] = df["invoice"].astype("string")
    return df


def test_segment_threshold_is_inclusive():
    assert segment("17850", 149.99) == RETAIL
    assert segment("17850", 150.0) == WHOLESALE


def test_segment_guest_customer_is_guest():
    assert segment(GUEST_CUSTOMER, 5000.0) == GUEST


def test_segment_customer_without_sales_is_retail():
    assert segment("17850", float("nan")) == RETAIL


def test_typical_order_value_sums_lines_and_takes_median():
    df = make_rows(
        {"invoice": "1", "quantity": 2, "price": 50.0},
        {"invoice": "1", "quantity": 1, "price": 100.0},
        {"invoice": "2", "quantity": 1, "price": 100.0},
        {"invoice": "3", "quantity": 1, "price": 300.0},
    )

    assert typical_order_values(df)["17850"] == 200.0


def test_typical_order_value_ignores_cancellations():
    df = make_rows({"invoice": "1", "price": 100.0}, {"invoice": "C2", "quantity": -50})

    assert typical_order_values(df)["17850"] == 100.0


def test_build_customers_uses_most_frequent_country():
    df = make_rows(
        {"invoice": "1", "country": "France"},
        {"invoice": "2", "country": "France"},
        {"invoice": "3", "country": "Germany"},
    )

    customer = build_customers(df).iloc[0]

    assert customer["country"] == "France"
    assert customer["segment"] == RETAIL
