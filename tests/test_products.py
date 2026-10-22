import pandas as pd
import pytest

from bootstrap.products import (
    MAX_COST_ADJUSTMENT,
    OTHER,
    Category,
    build_products,
    classify,
    cost_adjustment,
    keyword_pattern,
    load_categories,
)

CATEGORIES = [
    Category("Christmas", 0.50, keyword_pattern(["CHRISTMAS"])),
    Category("Candles & Lighting", 0.55, keyword_pattern(["CANDLE", "T-LIGHT"])),
    Category("Kitchen & Dining", 0.60, keyword_pattern(["MUG"])),
]
OTHER_COST_RATIO = 0.55


def category_of(description: str, stock_code: str = "85123A") -> str:
    return classify(stock_code, description, CATEGORIES, OTHER_COST_RATIO).category


def test_classify_uses_first_matching_category():
    assert category_of("CHRISTMAS CANDLE HOLDER") == "Christmas"


def test_classify_matches_plurals_and_ignores_case():
    assert category_of("Set of 3 Candles") == "Candles & Lighting"
    assert category_of("WHITE HANGING HEART T-LIGHT HOLDER") == "Candles & Lighting"


def test_classify_matches_whole_words_only():
    assert category_of("SMUGGLERS COVE SIGN") == OTHER


def test_classify_service_items():
    assert category_of("POSTAGE", stock_code="POST") == "Shipping"
    assert category_of("Discount", stock_code="D") == "Discount"
    assert category_of("Gift Voucher £20.00", stock_code="GIFT_0001_20") == "Gift Vouchers"


def test_cost_adjustment_is_repeatable_and_bounded():
    assert cost_adjustment("85123A") == cost_adjustment("85123A")
    assert cost_adjustment("85123A") != cost_adjustment("22423")
    assert abs(cost_adjustment("85123A")) <= MAX_COST_ADJUSTMENT


def make_rows(*rows: dict) -> pd.DataFrame:
    defaults = {"invoice": "536365", "stock_code": "M1", "description": "MUG", "price": 2.0}
    df = pd.DataFrame([defaults | row for row in rows])
    df["invoice"] = df["invoice"].astype("string")
    return df


def test_build_products_uses_median_sales_price_and_common_description():
    df = make_rows(
        {"price": 2.0, "description": "MUG"},
        {"price": 3.0, "description": "MUG"},
        {"price": 9.0, "description": "OLD MUG NAME"},
        {"invoice": "C536379", "price": 100.0},
    )

    product = build_products(df, CATEGORIES, OTHER_COST_RATIO).iloc[0]

    assert product["typical_price"] == 3.0
    assert product["description"] == "MUG"
    assert product["category"] == "Kitchen & Dining"


def test_build_products_costs_stock_items_from_category_ratio():
    product = build_products(make_rows({}), CATEGORIES, OTHER_COST_RATIO).iloc[0]

    expected = 2.0 * (0.60 + cost_adjustment("M1"))
    assert product["cost"] == pytest.approx(expected, abs=0.01)


def test_build_products_passes_shipping_through_at_cost():
    df = make_rows({"stock_code": "POST", "description": "POSTAGE", "price": 18.0})

    product = build_products(df, CATEGORIES, OTHER_COST_RATIO).iloc[0]

    assert product["cost"] == 18.0


def test_categories_file_is_valid():
    categories, other_cost_ratio = load_categories()

    names = [category.name for category in categories]
    assert len(names) == len(set(names))
    assert all(0 < category.cost_ratio < 1 for category in categories)
    assert 0 < other_cost_ratio < 1
