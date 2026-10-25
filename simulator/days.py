"""Generate one simulated day of sales and returns by replaying history.

Each simulated day replays the same weekday 52 weeks earlier (104 weeks for days more
than a year past the history, and so on), with deterministic variation and growth. The
rules are described in docs/simulator-rules.md.

Usage, as a dry run that does not touch ERPNext: uv run python -m simulator.days 2025-12-09
"""

import argparse
import hashlib
import math
from datetime import date, datetime, timedelta

import pandas as pd

from bootstrap.clean import is_cancellation
from bootstrap.load_invoices import prepare

REPLAY_STEP = timedelta(weeks=52)
SKIP_SHARE = 0.05
GROWTH_PER_YEAR = 0.05
MAX_QUANTITY_CHANGE = 0.20


def stable_fraction(*parts: object) -> float:
    """Return a number from 0 up to 1 that depends only on the given parts.

    A hash is used instead of a random number, so the same parts always give the same
    number, and every run of the simulator produces the same documents.
    """
    text = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode()).digest()
    return int.from_bytes(digest[:8]) / 2**64


def replay_years(day: date, history_end: date) -> int:
    """Return how many 52-week steps lie between a simulated day and the day it replays."""
    days_after = (day - history_end).days
    if days_after < 1:
        raise ValueError(f"{day} is not after the end of the history ({history_end})")
    return math.ceil(days_after / REPLAY_STEP.days)


def template_day(day: date, history_end: date) -> date:
    """Return the historical day that a simulated day replays."""
    return day - REPLAY_STEP * replay_years(day, history_end)


def copies(day: date, invoice: str, years: int) -> int:
    """Return how often a historical invoice is placed on the simulated day: 0, 1, or 2.

    About 5% of invoices are skipped, and 5% plus 5% per replayed year are placed twice,
    so the number of orders grows by about 5% a year.
    """
    draw = stable_fraction(day, invoice, "copies")
    if draw < SKIP_SHARE:
        return 0
    if draw >= 1 - (SKIP_SHARE + GROWTH_PER_YEAR * years):
        return 2
    return 1


def varied_quantity(quantity: int, *parts: object) -> int:
    """Return the quantity changed by up to 20% either way, keeping its sign, at least 1."""
    change = (2 * stable_fraction(*parts, "quantity") - 1) * MAX_QUANTITY_CHANGE
    varied = max(round(abs(quantity) * (1 + change)), 1)
    return int(math.copysign(varied, quantity))


def simulate_day(cleaned: pd.DataFrame, day: date, history_end: date) -> pd.DataFrame:
    """Return the simulated sales and return rows for one day, in the clean data's columns.

    Invoice keys look like SIM-20251209-1-536365: the simulated day, the copy number, and
    the historical invoice that is replayed.
    """
    template = template_day(day, history_end)
    years = replay_years(day, history_end)
    rows = cleaned[cleaned["invoice_date"].dt.date == template]

    simulated = []
    for invoice, lines in rows.groupby("invoice", sort=True):
        for copy in range(1, copies(day, invoice, years) + 1):
            key = f"SIM-{day:%Y%m%d}-{copy}-{invoice}"
            for number, line in enumerate(lines.itertuples(index=False), start=1):
                posted = datetime.combine(day, line.invoice_date.time())
                quantity = varied_quantity(line.quantity, day, invoice, copy, number)
                simulated.append(
                    line._asdict() | {"invoice": key, "invoice_date": posted, "quantity": quantity}
                )

    result = pd.DataFrame(simulated, columns=cleaned.columns)
    return result.astype({"invoice": "string", "invoice_date": "datetime64[us]"})


def main() -> None:
    """Simulate one day without touching ERPNext and compare it with the day it replays."""
    parser = argparse.ArgumentParser(description="Dry run of one simulated day.")
    parser.add_argument("day", help="the day to simulate, as YYYY-MM-DD, such as 2025-12-09")
    day = datetime.strptime(parser.parse_args().day, "%Y-%m-%d").date()

    cleaned, _ = prepare()
    history_end = cleaned["invoice_date"].max().date()
    template = template_day(day, history_end)
    original = cleaned[cleaned["invoice_date"].dt.date == template]
    simulated = simulate_day(cleaned, day, history_end)

    for label, rows, shown in [("Replayed", original, template), ("Simulated", simulated, day)]:
        returns = rows.loc[is_cancellation(rows), "invoice"].nunique()
        value = (rows["quantity"] * rows["price"]).sum()
        print(
            f"{label} {shown:%a %Y-%m-%d}: {rows['invoice'].nunique()} invoices "
            f"({returns} returns), {len(rows)} lines, net £{value:,.2f}"
        )


if __name__ == "__main__":
    main()
