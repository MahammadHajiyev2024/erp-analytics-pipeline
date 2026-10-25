from datetime import date

import pandas as pd

from bootstrap.clean import GUEST_CUSTOMER
from simulator.load import days_between, due_payments, month_days, new_customer_docs

HISTORY_END = date(2025, 12, 5)


def test_days_between_includes_both_ends():
    assert days_between(date(2025, 12, 30), date(2026, 1, 2)) == [
        date(2025, 12, 30),
        date(2025, 12, 31),
        date(2026, 1, 1),
        date(2026, 1, 2),
    ]


def test_month_days_start_after_the_history_in_its_last_month():
    december = month_days(date(2025, 12, 20), HISTORY_END)

    assert december[0] == date(2025, 12, 6)
    assert december[-1] == date(2025, 12, 31)


def test_month_days_cover_whole_later_months():
    february = month_days(date(2026, 2, 14), HISTORY_END)

    assert (february[0], february[-1], len(february)) == (date(2026, 2, 1), date(2026, 2, 28), 28)


def make_invoices(*invoices: dict) -> pd.DataFrame:
    defaults = {
        "name": "ACC-SINV-2026-00001",
        "custom_source_invoice": "SIM-20251207-1-574585",
        "customer": "17850",
        "posting_date": "2025-12-07",
        "grand_total": 12.0,
        "is_return": 0,
    }
    return pd.DataFrame([defaults | invoice for invoice in invoices])


def test_guest_customer_pays_on_the_day():
    invoices = make_invoices({"customer": GUEST_CUSTOMER})

    assert len(due_payments(invoices, date(2025, 12, 7))) == 1


def test_other_customers_pay_only_once_their_day_has_come():
    invoices = make_invoices({})

    assert due_payments(invoices, date(2025, 12, 16)) == []
    assert len(due_payments(invoices, date(2026, 1, 26))) == 1


def test_no_invoices_means_no_payments():
    assert due_payments(make_invoices().iloc[0:0], date(2025, 12, 7)) == []


def test_new_customers_copy_their_originals_segment():
    rows = pd.DataFrame(
        {
            "customer": ["SIM-20251209-1-14911", "SIM-20251209-1-14911", "17850"],
            "country": ["France", "France", "United Kingdom"],
        }
    )
    customers = pd.DataFrame({"segment": ["Wholesale", "Retail"]}, index=["14911", "17850"])

    docs = new_customer_docs(rows, customers)

    assert len(docs) == 1
    assert docs[0]["customer_name"] == "SIM-20251209-1-14911"
    assert docs[0]["customer_group"] == "Wholesale"
    assert docs[0]["territory"] == "France"
