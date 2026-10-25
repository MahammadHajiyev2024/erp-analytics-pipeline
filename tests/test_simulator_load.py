from datetime import date

from simulator.load import days_between, month_days

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
