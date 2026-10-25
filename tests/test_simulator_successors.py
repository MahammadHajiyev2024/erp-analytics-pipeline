from datetime import date

import pandas as pd

from bootstrap.products import Category, cost_adjustment, keyword_pattern
from simulator.successors import (
    SUCCESSORS_PER_MONTH,
    apply_successors,
    successor_code,
    successor_products,
    successors,
)

HISTORY_END = date(2025, 12, 5)
CODES = [f"2{number:04d}" for number in range(15)]
PRODUCTS = pd.DataFrame(
    {
        "description": [f"PRODUCT {code}" for code in CODES] + ["POSTAGE"],
        "item_type": ["stock"] * len(CODES) + ["service"],
        "category": ["Kitchen & Dining"] * len(CODES) + ["Shipping"],
        "typical_price": [10.0] * len(CODES) + [18.0],
        "cost": [6.0] * len(CODES) + [18.0],
    },
    index=pd.Index([*CODES, "POST"], name="stock_code"),
)


def sold_on(day: str, codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"stock_code": codes, "invoice_date": pd.Timestamp(day)})


# 10 December 2024 is replayed in December 2025, 7 January 2025 in January 2026.
CLEANED = pd.concat(
    [sold_on("2024-12-10", [*CODES, "POST"]), sold_on("2025-01-07", [*CODES, "POST"])]
)


def test_successor_code_adds_the_launch_year():
    assert successor_code("85123A", date(2025, 12, 1)) == "85123A-N25"


def test_successors_replace_ten_products_a_month_without_repeats():
    replaced = successors(CLEANED, PRODUCTS, HISTORY_END, date(2026, 1, 1))

    launches = [launch for _, launch in replaced.values()]
    assert launches.count(date(2025, 12, 1)) == SUCCESSORS_PER_MONTH
    assert launches.count(date(2026, 1, 1)) == len(CODES) - SUCCESSORS_PER_MONTH
    assert "POST" not in replaced


def test_successors_are_the_same_in_every_run():
    first = successors(CLEANED, PRODUCTS, HISTORY_END, date(2026, 1, 1))
    second = successors(CLEANED, PRODUCTS, HISTORY_END, date(2026, 1, 1))

    assert first == second


def test_successors_sell_instead_of_originals_from_their_launch():
    replaced = {"20000": ("20000-N26", date(2026, 1, 1))}
    rows = pd.DataFrame({"stock_code": ["20000", "20001"]})

    before = apply_successors(rows, replaced, date(2025, 12, 31))
    after = apply_successors(rows, replaced, date(2026, 1, 1))

    assert before["stock_code"].tolist() == ["20000", "20001"]
    assert after["stock_code"].tolist() == ["20000-N26", "20001"]


def test_successor_products_keep_category_and_price_with_their_own_cost():
    categories = [Category("Kitchen & Dining", 0.60, keyword_pattern(["MUG"]))]
    replaced = {"20000": ("20000-N26", date(2026, 1, 1))}

    product = successor_products(PRODUCTS, replaced, categories, 0.55).loc["20000-N26"]

    assert product["description"] == "PRODUCT 20000 - 2026 RANGE"
    assert product["category"] == "Kitchen & Dining"
    assert product["typical_price"] == 10.0
    assert product["cost"] == round(10.0 * (0.60 + cost_adjustment("20000-N26")), 2)
