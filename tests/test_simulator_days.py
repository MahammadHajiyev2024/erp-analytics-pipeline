from datetime import date

import pandas as pd

from bootstrap.clean import is_cancellation
from simulator.days import (
    copies,
    replay_years,
    simulate_day,
    stable_fraction,
    template_day,
    varied_quantity,
)

HISTORY_END = date(2025, 12, 5)


def make_rows(*rows: dict) -> pd.DataFrame:
    defaults = {
        "invoice": "574585",
        "stock_code": "85123A",
        "quantity": 10,
        "price": 2.55,
        "invoice_date": pd.Timestamp("2024-12-10 09:34"),
        "customer": "17850",
        "country": "United Kingdom",
    }
    df = pd.DataFrame([defaults | row for row in rows])
    return df.astype({"invoice": "string", "invoice_date": "datetime64[us]"})


def test_template_day_is_the_same_weekday_a_year_or_two_earlier():
    assert template_day(date(2025, 12, 9), HISTORY_END) == date(2024, 12, 10)
    assert template_day(date(2025, 12, 9), HISTORY_END).weekday() == date(2025, 12, 9).weekday()
    assert replay_years(date(2026, 12, 4), HISTORY_END) == 1
    assert replay_years(date(2026, 12, 5), HISTORY_END) == 2


def test_stable_fraction_is_repeatable():
    assert stable_fraction("2025-12-09", "574585") == stable_fraction("2025-12-09", "574585")
    assert stable_fraction("2025-12-09", "574585") != stable_fraction("2025-12-10", "574585")


def test_copies_skip_about_5_percent_and_double_about_10_percent_after_one_year():
    counts = [copies(date(2025, 12, 9), str(number), 1) for number in range(20000)]

    assert 0.04 < counts.count(0) / len(counts) < 0.06
    assert 0.09 < counts.count(2) / len(counts) < 0.11


def test_varied_quantity_stays_within_20_percent_and_keeps_its_sign():
    sales = [varied_quantity(100, "day", number) for number in range(1000)]
    returns = [varied_quantity(-100, "day", number) for number in range(1000)]

    assert min(sales) >= 80 and max(sales) <= 120
    assert max(returns) <= -80 and min(returns) >= -120
    assert varied_quantity(1, "day", "small") >= 1


def test_simulate_day_moves_rows_to_the_new_day_with_traceable_keys():
    rows = make_rows({}, {"invoice": "C574600", "quantity": -2})

    simulated = simulate_day(rows, date(2025, 12, 9), HISTORY_END)

    assert all(simulated["invoice_date"].dt.date == date(2025, 12, 9))
    assert all(simulated["invoice_date"].dt.strftime("%H:%M") == "09:34")
    assert all(simulated["invoice"].str.startswith("SIM-20251209-"))
    assert set(simulated["invoice"].str.split("-").str[-1]) <= {"574585", "C574600"}


def test_simulated_returns_are_still_cancellations():
    rows = make_rows({"invoice": "SIM-20251209-1-C574600"}, {"invoice": "SIM-20251209-1-574585"})

    assert is_cancellation(rows).tolist() == [True, False]
