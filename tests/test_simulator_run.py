from datetime import date

from simulator.run import VERIFY_WINDOW_DAYS, next_day, verification_window

HISTORY_END = date(2025, 12, 5)


def test_next_day_starts_after_the_history_when_nothing_is_simulated():
    assert next_day([], HISTORY_END) == date(2025, 12, 6)


def test_next_day_follows_the_latest_simulated_invoice():
    keys = ["SIM-20260113-1-574585", "SIM-20260114-2-C574600", "SIM-20251207-1-574001"]

    assert next_day(keys, HISTORY_END) == date(2026, 1, 15)


def test_verification_window_covers_the_last_60_days():
    window = verification_window(date(2026, 10, 23), HISTORY_END)

    assert len(window) == VERIFY_WINDOW_DAYS
    assert window[-1] == date(2026, 10, 23)


def test_verification_window_never_starts_before_the_simulation():
    window = verification_window(date(2025, 12, 20), HISTORY_END)

    assert window[0] == date(2025, 12, 6)
