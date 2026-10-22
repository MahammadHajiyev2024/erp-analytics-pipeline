"""Load the master data into ERPNext: groups, territories, suppliers, items, and customers.

The load only creates what is missing, so it can be run again at any time, and after an
interruption it continues where it stopped. Existing documents are never updated.
"""

import logging
import os
import tomllib
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from bootstrap.clean import clean
from bootstrap.customers import WHOLESALE, build_customers
from bootstrap.products import CATEGORIES_PATH, OTHER, build_products, load_categories
from bootstrap.source import load_source
from common.erpnext import create_missing, get_session

COMPANY = "Maple Home & Gift Ltd"
WAREHOUSE = "Stores - MHG"
SUPPLIER_GROUP = "Giftware"
UNIT = "Nos"
MAX_ITEM_NAME_LENGTH = 140

logger = logging.getLogger(__name__)


def load_suppliers(path: Path = CATEGORIES_PATH) -> dict[str, str]:
    """Return the supplier of each product category, including Other."""
    with path.open("rb") as file:
        config = tomllib.load(file)
    suppliers = {entry["name"]: entry["supplier"] for entry in config["category"]}
    suppliers[OTHER] = config["other_supplier"]
    return suppliers


def item_group_docs(products: pd.DataFrame) -> list[dict]:
    """Return one Item Group per product category."""
    return [
        {"item_group_name": name, "parent_item_group": "All Item Groups", "is_group": 0}
        for name in sorted(products["category"].unique())
    ]


def customer_group_docs(customers: pd.DataFrame) -> list[dict]:
    """Return one Customer Group per segment."""
    return [
        {
            "customer_group_name": name,
            "parent_customer_group": "All Customer Groups",
            "is_group": 0,
        }
        for name in sorted(customers["segment"].unique())
    ]


def territory_docs(df: pd.DataFrame) -> list[dict]:
    """Return one Territory per invoice country, so every invoice's country exists."""
    return [
        {"territory_name": name, "parent_territory": "All Territories", "is_group": 0}
        for name in sorted(df["country"].unique())
    ]


def supplier_group_docs() -> list[dict]:
    """Return the single Supplier Group that all suppliers belong to."""
    return [
        {
            "supplier_group_name": SUPPLIER_GROUP,
            "parent_supplier_group": "All Supplier Groups",
            "is_group": 0,
        },
    ]


def supplier_docs(suppliers: dict[str, str]) -> list[dict]:
    """Return one Supplier per distinct supplier name."""
    return [
        {
            "supplier_name": name,
            "supplier_group": SUPPLIER_GROUP,
            "supplier_type": "Company",
            "country": "United Kingdom",
        }
        for name in sorted(set(suppliers.values()))
    ]


def item_docs(products: pd.DataFrame, suppliers: dict[str, str]) -> list[dict]:
    """Return one Item per product; stock items get their cost and default supplier."""
    docs = []
    for product in products.itertuples(index=False):
        is_stock = product.item_type == "stock"
        doc = {
            "item_code": product.stock_code,
            "item_name": product.description[:MAX_ITEM_NAME_LENGTH],
            "description": product.description,
            "item_group": product.category,
            "stock_uom": UNIT,
            "is_stock_item": int(is_stock),
        }
        if is_stock:
            doc["valuation_rate"] = float(product.cost)
            doc["item_defaults"] = [
                {
                    "company": COMPANY,
                    "default_warehouse": WAREHOUSE,
                    "default_supplier": suppliers[product.category],
                },
            ]
        docs.append(doc)
    return docs


def customer_docs(customers: pd.DataFrame) -> list[dict]:
    """Return one Customer per customer; Wholesale customers are companies."""
    return [
        {
            "customer_name": customer.customer,
            "customer_type": "Company" if customer.segment == WHOLESALE else "Individual",
            "customer_group": customer.segment,
            "territory": customer.country,
        }
        for customer in customers.itertuples(index=False)
    ]


def main() -> None:
    """Load all master data into ERPNext as the bootstrap user."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    load_dotenv()
    base_url = os.environ["ERPNEXT_URL"]
    session = get_session(
        os.environ["ERPNEXT_BOOTSTRAP_API_KEY"], os.environ["ERPNEXT_BOOTSTRAP_API_SECRET"]
    )

    cleaned, _ = clean(load_source())
    categories, other_cost_ratio = load_categories()
    products = build_products(cleaned, categories, other_cost_ratio)
    customers = build_customers(cleaned)
    suppliers = load_suppliers()

    steps = [
        ("Item Group", item_group_docs(products), "item_group_name"),
        ("Customer Group", customer_group_docs(customers), "customer_group_name"),
        ("Territory", territory_docs(cleaned), "territory_name"),
        ("Supplier Group", supplier_group_docs(), "supplier_group_name"),
        ("Supplier", supplier_docs(suppliers), "supplier_name"),
        ("Item", item_docs(products, suppliers), "item_code"),
        ("Customer", customer_docs(customers), "customer_name"),
    ]
    for doctype, docs, name_field in steps:
        created = create_missing(session, base_url, doctype, docs, name_field)
        logger.info("%s: done, %d created", doctype, created)


if __name__ == "__main__":
    main()
