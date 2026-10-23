from datetime import date

import pandas as pd

from bootstrap.invoices import (
    EXPORT_TAX_TEMPLATE,
    RETURN_SERIES,
    SALES_SERIES,
    UK_TAX_TEMPLATE,
    in_month,
    purchase_invoice_docs,
    purchase_quantities,
    sales_invoice_docs,
)

PRODUCTS = pd.DataFrame(
    {
        "item_type": ["stock", "stock", "service"],
        "category": ["Candles & Lighting", "Kitchen & Dining", "Discount"],
        "cost": [1.57, 7.40, 0.0],
    },
    index=pd.Index(["85123A", "22423", "D"], name="stock_code"),
)
SUPPLIERS = {"Candles & Lighting": "Northern Candle Co.", "Kitchen & Dining": "Hearth & Table Ltd"}


def make_rows(*rows: dict) -> pd.DataFrame:
    defaults = {
        "invoice": "536365",
        "stock_code": "85123A",
        "quantity": 6,
        "price": 2.55,
        "invoice_date": pd.Timestamp("2025-11-15 08:26"),
        "customer": "17850",
        "country": "United Kingdom",
    }
    df = pd.DataFrame([defaults | row for row in rows])
    df["invoice"] = df["invoice"].astype("string")
    return df


def test_in_month_keeps_only_that_month():
    df = make_rows(
        {"invoice_date": pd.Timestamp("2025-10-31 23:59")},
        {"invoice_date": pd.Timestamp("2025-11-01 00:00")},
        {"invoice_date": pd.Timestamp("2025-12-01 00:00")},
    )

    assert len(in_month(df, 2025, 11)) == 1


def test_sales_invoice_has_dates_due_date_and_source_key():
    doc = sales_invoice_docs(make_rows({}), PRODUCTS)[0]

    assert doc["custom_source_invoice"] == "536365"
    assert doc["posting_date"] == "2025-11-15"
    assert doc["posting_time"] == "08:26:00"
    assert doc["due_date"] == "2025-12-15"
    assert doc["naming_series"] == SALES_SERIES
    assert doc["docstatus"] == 1


def test_sales_invoice_charges_uk_vat_and_zero_rates_exports():
    uk = sales_invoice_docs(make_rows({}), PRODUCTS)[0]
    export = sales_invoice_docs(make_rows({"country": "France"}), PRODUCTS)[0]

    assert uk["taxes_and_charges"] == UK_TAX_TEMPLATE
    assert uk["taxes"][0]["rate"] == 20.0
    assert export["taxes_and_charges"] == EXPORT_TAX_TEMPLATE
    assert export["taxes"][0]["rate"] == 0.0


def test_sales_invoice_keeps_one_line_per_source_row():
    rows = make_rows({"stock_code": "85123A"}, {"stock_code": "22423"}, {"invoice": "536366"})

    docs = sales_invoice_docs(rows, PRODUCTS)

    assert [len(doc["items"]) for doc in docs] == [2, 1]


def test_return_uses_return_series_and_incoming_rate_for_stock_items():
    rows = make_rows(
        {"invoice": "C536379", "quantity": -2},
        {"invoice": "C536379", "stock_code": "D", "quantity": -1, "price": 27.50},
    )

    doc = sales_invoice_docs(rows, PRODUCTS)[0]

    assert doc["is_return"] == 1
    assert doc["naming_series"] == RETURN_SERIES
    assert doc["items"][0]["incoming_rate"] == 1.57
    assert "incoming_rate" not in doc["items"][1]


def test_purchase_quantities_add_buffer_and_ignore_returns_and_services():
    rows = make_rows(
        {"quantity": 6},
        {"quantity": 4},
        {"invoice": "C536379", "quantity": -3},
        {"stock_code": "D", "quantity": 1},
    )

    quantities = purchase_quantities(rows, PRODUCTS)

    assert quantities.to_dict() == {"85123A": 12}


def test_purchase_invoices_group_items_by_supplier_at_cost():
    rows = make_rows({"quantity": 10}, {"stock_code": "22423", "quantity": 5})

    docs = purchase_invoice_docs(rows, PRODUCTS, SUPPLIERS, date(2025, 11, 1))

    assert [doc["supplier"] for doc in docs] == ["Hearth & Table Ltd", "Northern Candle Co."]
    candle = docs[1]
    assert candle["bill_no"] == "2025-11 Northern Candle Co."
    assert candle["posting_date"] == "2025-11-01"
    assert candle["items"] == [
        {"item_code": "85123A", "qty": 12, "rate": 1.57, "warehouse": "Stores - MHG"}
    ]
