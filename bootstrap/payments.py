"""Turn submitted sales invoices into payments and refunds.

Customers pay invoices, and MHG refunds returns, on a fixed day per invoice: the same day
for the Guest Customer, otherwise 10 to 50 days after the invoice (docs/bootstrap-rules.md).
"""

import hashlib

import pandas as pd

from bootstrap.clean import GUEST_CUSTOMER
from bootstrap.load_master import COMPANY

BANK_ACCOUNT = "Business Bank Account - MHG"
DEBTORS_ACCOUNT = "Debtors - MHG"
MIN_DELAY_DAYS = 10
MAX_DELAY_DAYS = 50


def payment_delay_days(source_invoice: str, customer: str) -> int:
    """Return how many days after the invoice it is paid or refunded.

    A hash of the source invoice number is used instead of a random number, so every run
    produces the same payment dates.
    """
    if customer == GUEST_CUSTOMER:
        return 0
    digest = hashlib.sha256(source_invoice.encode()).digest()
    span = MAX_DELAY_DAYS - MIN_DELAY_DAYS + 1
    return MIN_DELAY_DAYS + int.from_bytes(digest[:8]) % span


def payment_doc(invoice: pd.Series) -> dict:
    """Return the Payment Entry that settles one submitted sales invoice or return.

    invoice needs name, custom_source_invoice, customer, posting_date, grand_total, and
    is_return. Invoices are received into the bank; returns are refunded from it.
    """
    source = invoice["custom_source_invoice"]
    delay = payment_delay_days(source, invoice["customer"])
    posted = pd.Timestamp(invoice["posting_date"])
    paid_on = (posted + pd.Timedelta(days=delay)).strftime("%Y-%m-%d")
    is_refund = bool(invoice["is_return"])
    amount = abs(float(invoice["grand_total"]))
    return {
        "payment_type": "Pay" if is_refund else "Receive",
        "party_type": "Customer",
        "party": invoice["customer"],
        "company": COMPANY,
        "posting_date": paid_on,
        "paid_from": BANK_ACCOUNT if is_refund else DEBTORS_ACCOUNT,
        "paid_to": DEBTORS_ACCOUNT if is_refund else BANK_ACCOUNT,
        "paid_amount": amount,
        "received_amount": amount,
        "reference_no": source,
        "reference_date": paid_on,
        "references": [
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": invoice["name"],
                "allocated_amount": float(invoice["grand_total"]),
            },
        ],
        "docstatus": 1,
    }


def payment_docs(invoices: pd.DataFrame) -> list[dict]:
    """Return one Payment Entry per submitted sales invoice or return."""
    return [payment_doc(invoice) for _, invoice in invoices.iterrows()]
