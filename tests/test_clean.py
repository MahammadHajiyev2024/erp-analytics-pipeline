import pandas as pd

from bootstrap.clean import (
    GUEST_CUSTOMER,
    add_customer,
    clean,
    exclude_adjustments,
    exclude_invalid_prices,
    exclude_misplaced_discounts,
    exclude_non_sales_codes,
    remove_duplicates,
    shift_dates,
)


def make_rows(*rows: dict) -> pd.DataFrame:
    """Build source rows; each dict overrides the defaults of one row."""
    defaults = {
        "invoice": "536365",
        "stock_code": "85123A",
        "description": "WHITE HANGING HEART T-LIGHT HOLDER",
        "quantity": 6,
        "invoice_date": pd.Timestamp("2010-12-01 08:26"),
        "price": 2.55,
        "customer_id": 17850,
        "country": "United Kingdom",
    }
    df = pd.DataFrame([defaults | row for row in rows])
    df["invoice"] = df["invoice"].astype("string")
    df["stock_code"] = df["stock_code"].astype("string")
    df["customer_id"] = df["customer_id"].astype("Int64")
    return df


def test_remove_duplicates_keeps_one_copy():
    df = make_rows({}, {}, {"quantity": 12})

    assert len(remove_duplicates(df)) == 2


def test_exclude_non_sales_codes_ignores_case():
    df = make_rows(
        {"stock_code": "AMAZONFEE"},
        {"stock_code": "m"},
        {"stock_code": "BANK CHARGES"},
        {"stock_code": "85123A"},
        {"stock_code": "gift_0001_20"},
    )

    kept = exclude_non_sales_codes(df)["stock_code"].tolist()

    assert kept == ["85123A", "gift_0001_20"]


def test_exclude_invalid_prices():
    df = make_rows({"price": 0.0}, {"price": -11062.06}, {"price": 0.001}, {"price": 0.01})

    assert exclude_invalid_prices(df)["price"].tolist() == [0.01]


def test_exclude_adjustments_keeps_cancellations():
    df = make_rows(
        {"invoice": "536365", "quantity": -3},
        {"invoice": "C536379", "quantity": -3},
        {"invoice": "536366", "quantity": 3},
    )

    assert exclude_adjustments(df)["invoice"].tolist() == ["C536379", "536366"]


def test_exclude_misplaced_discounts_keeps_discounts_on_cancellations():
    df = make_rows(
        {"invoice": "536365", "stock_code": "D", "quantity": 1},
        {"invoice": "C536379", "stock_code": "D", "quantity": -1},
    )

    assert exclude_misplaced_discounts(df)["invoice"].tolist() == ["C536379"]


def test_add_customer_uses_guest_customer_for_missing_ids():
    df = make_rows({"customer_id": 17850}, {"customer_id": None})

    assert add_customer(df)["customer"].tolist() == ["17850", GUEST_CUSTOMER]


def test_clean_reports_rows_removed_per_rule():
    df = make_rows({}, {}, {"price": 0.0}, {"stock_code": "M"})

    cleaned, removed = clean(df)

    assert len(cleaned) == 1
    assert removed["remove_duplicates"] == 1
    assert removed["exclude_non_sales_codes"] == 1
    assert removed["exclude_invalid_prices"] == 1


def test_shift_dates_moves_first_and_last_day():
    df = make_rows(
        {"invoice_date": pd.Timestamp("2009-12-01 07:45")},
        {"invoice_date": pd.Timestamp("2011-12-09 12:50")},
    )

    shifted = shift_dates(df)["invoice_date"].tolist()

    assert shifted == [pd.Timestamp("2023-11-28 07:45"), pd.Timestamp("2025-12-05 12:50")]


def test_shift_dates_keeps_weekdays():
    dates = pd.date_range("2010-01-01", periods=7, freq="D")
    df = make_rows(*({"invoice_date": date} for date in dates))

    shifted = shift_dates(df)["invoice_date"]

    assert shifted.dt.dayofweek.tolist() == df["invoice_date"].dt.dayofweek.tolist()


def test_clean_shifts_dates():
    df = make_rows({"invoice_date": pd.Timestamp("2010-12-01 08:26")})

    cleaned, _ = clean(df)

    assert cleaned["invoice_date"].iloc[0] == pd.Timestamp("2024-11-27 08:26")
