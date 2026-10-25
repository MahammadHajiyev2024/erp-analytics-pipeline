"""Successor products: each simulated month, about 10 products are replaced by a new range.

The choice of products depends only on the data and a hash, so every month's successors
can be recalculated from scratch in any run (docs/simulator-rules.md).
"""

from datetime import date, timedelta

import pandas as pd

from bootstrap.products import Category, cost_adjustment
from simulator.days import stable_fraction, template_day

SUCCESSORS_PER_MONTH = 10


def successor_code(stock_code: str, launch: date) -> str:
    """Return the successor's stock code, such as 85123A-N25 for a 2025 launch."""
    return f"{stock_code}-N{launch:%y}"


def simulated_months(history_end: date, last_month: date) -> list[date]:
    """Return the first day of every simulated month, from the history's end to last_month."""
    first = history_end.replace(day=1)
    return [day.date() for day in pd.date_range(first, last_month, freq="MS")]


def replayed_days(month_start: date, history_end: date) -> set[date]:
    """Return the historical days that the month's simulated days replay."""
    month_end = (pd.Timestamp(month_start) + pd.offsets.MonthEnd(0)).date()
    first = max(month_start, history_end + timedelta(days=1))
    days = pd.date_range(first, month_end, freq="D").date
    return {template_day(day, history_end) for day in days}


def successors(
    cleaned: pd.DataFrame, products: pd.DataFrame, history_end: date, last_month: date
) -> dict[str, tuple[str, date]]:
    """Return each replaced product's successor code and launch month, up to last_month.

    Each month, the stock items sold on the days it replays are sorted by a hash, and the
    first SUCCESSORS_PER_MONTH that have not been replaced yet are chosen. products must
    be indexed by stock code.
    """
    stock_items = set(products.index[products["item_type"] == "stock"])
    sold_dates = cleaned["invoice_date"].dt.date
    replaced: dict[str, tuple[str, date]] = {}
    for month_start in simulated_months(history_end, last_month):
        sold = cleaned.loc[sold_dates.isin(replayed_days(month_start, history_end)), "stock_code"]
        candidates = sorted(
            (set(sold) & stock_items) - set(replaced),
            key=lambda code: stable_fraction(month_start, code, "successor"),
        )
        for code in candidates[:SUCCESSORS_PER_MONTH]:
            replaced[code] = (successor_code(code, month_start), month_start)
    return replaced


def apply_successors(
    rows: pd.DataFrame, replaced: dict[str, tuple[str, date]], day: date
) -> pd.DataFrame:
    """Return the rows with each replaced product sold as its successor from its launch on."""
    launched = {code: new for code, (new, launch) in replaced.items() if launch <= day}
    return rows.assign(stock_code=rows["stock_code"].replace(launched))


def successor_products(
    products: pd.DataFrame,
    replaced: dict[str, tuple[str, date]],
    categories: list[Category],
    other_cost_ratio: float,
) -> pd.DataFrame:
    """Return the successors as products, indexed by stock code, with their own costs.

    A successor keeps its original's category and typical price; its cost uses the
    category's ratio and the cost adjustment of its own code. products must be indexed
    by stock code.
    """
    ratios = {category.name: category.cost_ratio for category in categories}
    rows = []
    for code, (new_code, launch) in replaced.items():
        original = products.loc[code]
        ratio = ratios.get(original["category"], other_cost_ratio)
        rows.append(
            {
                "stock_code": new_code,
                "description": f"{original['description']} - {launch:%Y} RANGE",
                "item_type": "stock",
                "category": original["category"],
                "typical_price": original["typical_price"],
                "cost": round(original["typical_price"] * (ratio + cost_adjustment(new_code)), 2),
            }
        )
    return pd.DataFrame(rows, columns=["stock_code", *products.columns]).set_index("stock_code")
