from datetime import date

from bootstrap.load_history import months


def test_months_include_both_ends_and_cross_years():
    selected = months(date(2023, 11, 1), date(2024, 2, 1))

    assert selected == [date(2023, 11, 1), date(2023, 12, 1), date(2024, 1, 1), date(2024, 2, 1)]


def test_months_with_one_month():
    assert months(date(2025, 11, 1), date(2025, 11, 1)) == [date(2025, 11, 1)]
