import pandas as pd

from bootstrap.verify import (
    compare,
    expected_purchases,
    expected_sales,
    unsettled,
    wrong_customers,
)


def make_rows(*rows: dict) -> pd.DataFrame:
    defaults = {
        "invoice": "536365",
        "stock_code": "85123A",
        "quantity": 6,
        "price": 2.55,
        "customer": "17850",
        "country": "United Kingdom",
    }
    df = pd.DataFrame([defaults | row for row in rows])
    df["invoice"] = df["invoice"].astype("string")
    return df


def stored(**invoices: dict) -> pd.DataFrame:
    return pd.DataFrame.from_dict(invoices, orient="index")


def test_expected_sales_adds_rounded_lines_and_uk_vat():
    rows = make_rows({"quantity": 3, "price": 0.85}, {"quantity": 1, "price": 1.25})

    invoice = expected_sales(rows).loc["536365"]

    assert invoice["total_qty"] == 4
    assert invoice["net_total"] == 3.80
    assert invoice["total_taxes_and_charges"] == 0.76
    assert invoice["grand_total"] == 4.56


def test_expected_sales_has_no_vat_on_exports():
    invoice = expected_sales(make_rows({"country": "France"})).loc["536365"]

    assert invoice["total_taxes_and_charges"] == 0.0
    assert invoice["grand_total"] == invoice["net_total"]


def test_compare_accepts_a_penny_but_not_more():
    expected = stored(A={"net_total": 10.00}, B={"net_total": 10.00})
    actual = stored(A={"net_total": 10.01}, B={"net_total": 10.02})

    problems = compare(expected, actual, ["net_total"], "Sales invoice")

    assert problems == ["Sales invoice B net_total: expected 10.0, ERPNext 10.02"]


def test_compare_reports_missing_and_unexpected_documents():
    expected = stored(A={"net_total": 1.0}, B={"net_total": 1.0})
    actual = stored(B={"net_total": 1.0}, C={"net_total": 1.0})

    problems = compare(expected, actual, ["net_total"], "Sales invoice")

    assert problems == [
        "Sales invoice missing from ERPNext: A",
        "Sales invoice not in the source data: C",
    ]


def test_wrong_customers_and_unsettled_invoices_are_reported():
    expected = stored(A={"customer": "17850"})
    actual = stored(A={"customer": "12346", "outstanding_amount": 12.24})

    assert wrong_customers(expected, actual) == ["Sales invoice A has the wrong customer"]
    assert unsettled(actual) == ["Sales invoice A is not settled"]


def test_expected_purchases_total_each_supplier():
    products = pd.DataFrame(
        {"item_type": ["stock"], "category": ["Candles & Lighting"], "cost": [1.57]},
        index=pd.Index(["85123A"], name="stock_code"),
    )
    suppliers = {"Candles & Lighting": "Northern Candle Co."}

    purchases = expected_purchases(make_rows({"quantity": 10}), products, suppliers)

    assert purchases.loc["Northern Candle Co.", "total_qty"] == 12
    assert purchases.loc["Northern Candle Co.", "net_total"] == 18.84
