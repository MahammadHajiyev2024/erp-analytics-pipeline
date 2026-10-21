"""Build the product list: one row per stock code, with its category and cost.

The rules are described in docs/bootstrap-rules.md; the category keywords and cost ratios
live in categories.toml next to this file.
"""

import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bootstrap.clean import DISCOUNT_CODE, clean, is_cancellation
from bootstrap.source import load_source

CATEGORIES_PATH = Path(__file__).with_name("categories.toml")
SHIPPING_CODES = ["POST", "DOT", "C2"]
VOUCHER_PREFIX = "gift_"
OTHER = "Other"
MAX_COST_ADJUSTMENT = 0.05


@dataclass(frozen=True)
class Category:
    name: str
    cost_ratio: float
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class Classification:
    item_type: str
    category: str
    cost_ratio: float


def load_categories(path: Path = CATEGORIES_PATH) -> tuple[list[Category], float]:
    """Return the keyword categories in order, and the cost ratio for unmatched products."""
    with path.open("rb") as file:
        config = tomllib.load(file)
    categories = [
        Category(entry["name"], entry["cost_ratio"], keyword_pattern(entry["keywords"]))
        for entry in config["category"]
    ]
    return categories, config["other_cost_ratio"]


def keyword_pattern(keywords: list[str]) -> re.Pattern[str]:
    """Match any keyword as a whole word, with an optional plural S or ES, ignoring case."""
    alternatives = "|".join(re.escape(keyword) for keyword in keywords)
    return re.compile(rf"\b(?:{alternatives})(?:S|ES)?\b", flags=re.IGNORECASE)


def classify(
    stock_code: str, description: str, categories: list[Category], other_cost_ratio: float
) -> Classification:
    """Return the item type, category, and cost ratio of one product."""
    if stock_code in SHIPPING_CODES:
        return Classification("service", "Shipping", 1.0)
    if stock_code == DISCOUNT_CODE:
        return Classification("service", "Discount", 0.0)
    if stock_code.startswith(VOUCHER_PREFIX):
        return Classification("service", "Gift Vouchers", 1.0)
    for category in categories:
        if category.pattern.search(description):
            return Classification("stock", category.name, category.cost_ratio)
    return Classification("stock", OTHER, other_cost_ratio)


def cost_adjustment(stock_code: str) -> float:
    """Return a fixed adjustment of up to 5 percentage points, derived from the stock code.

    A hash of the code is used instead of a random number, so the same code always gets the
    same adjustment and every run of the bootstrap produces the same costs.
    """
    digest = hashlib.sha256(stock_code.encode()).digest()
    fraction = int.from_bytes(digest[:8]) / 2**64
    return (2 * fraction - 1) * MAX_COST_ADJUSTMENT


def typical_prices(df: pd.DataFrame) -> pd.Series:
    """Return each stock code's median price on sales, or on any row if it was never sold."""
    sales = df[~is_cancellation(df)].groupby("stock_code")["price"].median()
    any_row = df.groupby("stock_code")["price"].median()
    return sales.reindex(any_row.index).fillna(any_row)


def descriptions(df: pd.DataFrame) -> pd.Series:
    """Return each stock code's most frequent description."""
    described = df.dropna(subset=["description"])
    return described.groupby("stock_code")["description"].agg(lambda names: names.mode().iloc[0])


def build_products(
    df: pd.DataFrame, categories: list[Category], other_cost_ratio: float
) -> pd.DataFrame:
    """Return one row per stock code with description, category, typical price, and cost."""
    prices = typical_prices(df)
    names = descriptions(df).reindex(prices.index)
    names = names.fillna(pd.Series(prices.index, index=prices.index))

    rows = []
    for stock_code, price in prices.items():
        description = names[stock_code]
        classification = classify(stock_code, description, categories, other_cost_ratio)
        ratio = classification.cost_ratio
        if classification.item_type == "stock":
            ratio += cost_adjustment(stock_code)
        rows.append(
            {
                "stock_code": stock_code,
                "description": description,
                "item_type": classification.item_type,
                "category": classification.category,
                "typical_price": price,
                "cost": round(price * ratio, 2),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    """Build the product list and report how the products fall into categories."""
    cleaned, _ = clean(load_source())
    categories, other_cost_ratio = load_categories()
    products = build_products(cleaned, categories, other_cost_ratio)

    print(f"Products: {len(products):,}")
    counts = products["category"].value_counts()
    for category, count in counts.items():
        print(f"  {category}: {count:,} ({count / len(products):.1%})")

    stock = products[products["item_type"] == "stock"]
    margin = 1 - stock["cost"].sum() / stock["typical_price"].sum()
    print(f"Average gross margin at typical prices: {margin:.1%}")

    words = stock.loc[stock["category"] == OTHER, "description"].str.split().explode()
    print("Most common words in Other:")
    print(words.value_counts().head(30).to_string())


if __name__ == "__main__":
    main()
