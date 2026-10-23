import pandas as pd

from bootstrap.clean import GUEST_CUSTOMER
from bootstrap.payments import (
    BANK_ACCOUNT,
    DEBTORS_ACCOUNT,
    MAX_DELAY_DAYS,
    MIN_DELAY_DAYS,
    payment_delay_days,
    payment_doc,
)


def make_invoice(**fields) -> pd.Series:
    defaults = {
        "name": "ACC-SINV-2026-00001",
        "custom_source_invoice": "536365",
        "customer": "17850",
        "posting_date": "2025-11-15",
        "grand_total": 12.0,
        "is_return": 0,
    }
    return pd.Series(defaults | fields)


def test_payment_delay_is_repeatable_and_within_terms():
    delays = [payment_delay_days(str(number), "17850") for number in range(536365, 537365)]

    assert payment_delay_days("536365", "17850") == payment_delay_days("536365", "17850")
    assert min(delays) == MIN_DELAY_DAYS
    assert max(delays) == MAX_DELAY_DAYS


def test_guest_customer_pays_the_same_day():
    assert payment_delay_days("536365", GUEST_CUSTOMER) == 0


def test_invoice_is_received_from_debtors_into_the_bank():
    doc = payment_doc(make_invoice())

    assert doc["payment_type"] == "Receive"
    assert (doc["paid_from"], doc["paid_to"]) == (DEBTORS_ACCOUNT, BANK_ACCOUNT)
    assert doc["paid_amount"] == 12.0
    assert doc["references"][0]["reference_name"] == "ACC-SINV-2026-00001"
    assert doc["references"][0]["allocated_amount"] == 12.0
    assert doc["reference_no"] == "536365"


def test_payment_date_follows_the_delay():
    doc = payment_doc(make_invoice())

    delay = payment_delay_days("536365", "17850")
    expected = (pd.Timestamp("2025-11-15") + pd.Timedelta(days=delay)).strftime("%Y-%m-%d")
    assert doc["posting_date"] == expected
    assert doc["reference_date"] == expected


def test_return_is_refunded_from_the_bank_with_negative_allocation():
    doc = payment_doc(make_invoice(custom_source_invoice="C536379", grand_total=-12.0, is_return=1))

    assert doc["payment_type"] == "Pay"
    assert (doc["paid_from"], doc["paid_to"]) == (BANK_ACCOUNT, DEBTORS_ACCOUNT)
    assert doc["paid_amount"] == 12.0
    assert doc["references"][0]["allocated_amount"] == -12.0
