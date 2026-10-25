from datetime import date, timedelta

import pandas as pd

from bootstrap.clean import GUEST_CUSTOMER
from bootstrap.payments import payment_delay_days
from simulator.verify import payment_day, payment_problems, set_problems

KEY = "SIM-20260107-1-574585"
POSTED = date(2026, 1, 7)


def invoice(customer: str = "17850", outstanding: float = 12.0) -> pd.DataFrame:
    row = {
        "customer": customer,
        "posting_date": POSTED.isoformat(),
        "grand_total": 12.0,
        "outstanding_amount": outstanding,
    }
    return pd.DataFrame([row], index=[KEY])


def test_payment_day_follows_the_payment_rule():
    assert payment_day(KEY, GUEST_CUSTOMER, POSTED) == POSTED
    assert payment_day(KEY, "17850", POSTED) == POSTED + timedelta(
        days=payment_delay_days(KEY, "17850")
    )


def test_open_invoices_are_fine_until_their_payment_day():
    due = payment_day(KEY, "17850", POSTED)

    assert payment_problems(invoice(outstanding=12.0), due - timedelta(days=1)) == []
    assert payment_problems(invoice(outstanding=0.0), due) == []


def test_payment_problems_report_late_and_early_settlement():
    due = payment_day(KEY, "17850", POSTED)

    assert payment_problems(invoice(outstanding=12.0), due) == [
        f"Sales invoice {KEY} should be settled on {due} but is open"
    ]
    assert payment_problems(invoice(outstanding=0.0), due - timedelta(days=1)) == [
        f"Sales invoice {KEY} is not due until {due} but is settled"
    ]


def test_set_problems_report_missing_and_unexpected_keys():
    problems = set_problems({"A", "B"}, {"B", "C"}, "Cancellation")

    assert problems == ["Cancellation missing: A", "Cancellation not expected: C"]
