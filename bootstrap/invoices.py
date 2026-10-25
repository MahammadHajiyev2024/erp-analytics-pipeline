"""Turn one month of clean source data into ERPNext purchase and sales invoices.

The rules are described in docs/bootstrap-rules.md. Everything ERPNext needs is sent
explicitly (rates, warehouse, tax rows, incoming rates on returns), because API requests
do not get the defaults that ERPNext's screens fill in.
"""

import math
from datetime import date, timedelta

import pandas as pd

from bootstrap.clean import is_cancellation, is_return_invoice
from bootstrap.load_master import WAREHOUSE

UK = "United Kingdom"
UK_TAX_TEMPLATE = "United Kingdom Tax - MHG"
EXPORT_TAX_TEMPLATE = "Zero-Rated Export - MHG"
VAT_ACCOUNT = "VAT - MHG"
UK_VAT_RATE = 20.0
PAYMENT_TERMS_DAYS = 30
SALES_SERIES = "ACC-SINV-.YYYY.-"
RETURN_SERIES = "ACC-SINV-RET-.YYYY.-"
PURCHASE_BUFFER = 0.20

# Fields every invoice sends, so ERPNext uses the given dates, updates stock, does not
# round totals, and submits the document in the same request.
COMMON_FIELDS = {
    "set_posting_time": 1,
    "update_stock": 1,
    "set_warehouse": WAREHOUSE,
    "disable_rounded_total": 1,
    "docstatus": 1,
}


def in_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """Return the rows whose invoice date falls in the given month."""
    dates = df["invoice_date"]
    return df[(dates.dt.year == year) & (dates.dt.month == month)]


def vat(country: str) -> tuple[str, list[dict]]:
    """Return the tax template and tax rows for an invoice to the given country."""
    if country == UK:
        template, rate, description = UK_TAX_TEMPLATE, UK_VAT_RATE, "VAT 20%"
    else:
        template, rate, description = EXPORT_TAX_TEMPLATE, 0.0, "VAT zero-rated export"
    row = {
        "charge_type": "On Net Total",
        "account_head": VAT_ACCOUNT,
        "description": description,
        "rate": rate,
    }
    return template, [row]


def sales_line(row, products: pd.DataFrame, is_return: bool) -> dict:
    """Return one invoice line; stock returns carry the item's cost as incoming rate."""
    line = {
        "item_code": row.stock_code,
        "qty": int(row.quantity),
        "rate": float(row.price),
        "warehouse": WAREHOUSE,
    }
    product = products.loc[row.stock_code]
    if is_return and product["item_type"] == "stock":
        line["incoming_rate"] = float(product["cost"])
    return line


def sales_invoice_docs(rows: pd.DataFrame, products: pd.DataFrame) -> list[dict]:
    """Return one Sales Invoice per source invoice; cancellations become returns.

    products must be indexed by stock code.
    """
    docs = []
    for invoice, lines in rows.groupby("invoice", sort=True):
        first = lines.iloc[0]
        is_return = is_return_invoice(invoice)
        posted = first["invoice_date"]
        template, taxes = vat(first["country"])
        docs.append(
            COMMON_FIELDS
            | {
                "naming_series": RETURN_SERIES if is_return else SALES_SERIES,
                "custom_source_invoice": invoice,
                "customer": first["customer"],
                "is_return": int(is_return),
                "posting_date": posted.strftime("%Y-%m-%d"),
                "posting_time": posted.strftime("%H:%M:%S"),
                "due_date": (posted + timedelta(days=PAYMENT_TERMS_DAYS)).strftime("%Y-%m-%d"),
                "territory": first["country"],
                "taxes_and_charges": template,
                "taxes": taxes,
                "items": [
                    sales_line(row, products, is_return) for row in lines.itertuples(index=False)
                ],
            }
        )
    return docs


def purchase_quantities(rows: pd.DataFrame, products: pd.DataFrame) -> pd.Series:
    """Return how many units of each stock item to buy: the month's sales plus the buffer.

    products must be indexed by stock code.
    """
    sales = rows[~is_cancellation(rows)]
    sold = sales.groupby("stock_code")["quantity"].sum()
    stock_items = products.index[products["item_type"] == "stock"]
    sold = sold[sold.index.isin(stock_items)]
    return sold.map(lambda quantity: math.ceil(quantity * (1 + PURCHASE_BUFFER)))


def purchase_invoice_docs(
    rows: pd.DataFrame, products: pd.DataFrame, suppliers: dict[str, str], purchase_date: date
) -> list[dict]:
    """Return one Purchase Invoice per supplier, dated before the month's first sale.

    products must be indexed by stock code; suppliers maps each category to its supplier.
    """
    quantities = purchase_quantities(rows, products)
    lines = pd.DataFrame(
        {
            "stock_code": quantities.index,
            "qty": quantities.to_numpy(),
            "supplier": [suppliers[products.at[code, "category"]] for code in quantities.index],
        }
    )
    posted = purchase_date.strftime("%Y-%m-%d")
    due = (purchase_date + timedelta(days=PAYMENT_TERMS_DAYS)).strftime("%Y-%m-%d")
    docs = []
    for supplier, items in lines.groupby("supplier", sort=True):
        docs.append(
            COMMON_FIELDS
            | {
                "supplier": supplier,
                "bill_no": f"{purchase_date:%Y-%m} {supplier}",
                "bill_date": posted,
                "posting_date": posted,
                "posting_time": "00:00:00",
                "due_date": due,
                "items": [
                    {
                        "item_code": item.stock_code,
                        "qty": int(item.qty),
                        "rate": float(products.at[item.stock_code, "cost"]),
                        "warehouse": WAREHOUSE,
                    }
                    for item in items.sort_values("stock_code").itertuples(index=False)
                ],
            }
        )
    return docs
