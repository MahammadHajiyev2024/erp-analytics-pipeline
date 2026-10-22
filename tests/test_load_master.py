import pandas as pd

from bootstrap.load_master import (
    COMPANY,
    MAX_ITEM_NAME_LENGTH,
    customer_docs,
    item_docs,
    load_suppliers,
    supplier_docs,
    territory_docs,
)
from bootstrap.products import OTHER, load_categories

SUPPLIERS = {"Kitchen & Dining": "Hearth & Table Ltd", OTHER: "Cosy Home Goods Ltd"}


def make_products(*rows: dict) -> pd.DataFrame:
    defaults = {
        "stock_code": "22423",
        "description": "REGENCY CAKESTAND 3 TIER",
        "item_type": "stock",
        "category": "Kitchen & Dining",
        "typical_price": 12.75,
        "cost": 7.40,
    }
    return pd.DataFrame([defaults | row for row in rows])


def test_item_docs_give_stock_items_cost_and_supplier():
    doc = item_docs(make_products({}), SUPPLIERS)[0]

    assert doc["is_stock_item"] == 1
    assert doc["valuation_rate"] == 7.40
    assert doc["item_defaults"][0]["company"] == COMPANY
    assert doc["item_defaults"][0]["default_supplier"] == "Hearth & Table Ltd"


def test_item_docs_keep_service_items_out_of_stock():
    shipping = {"stock_code": "POST", "description": "POSTAGE", "item_type": "service"}
    products = make_products(shipping | {"category": "Shipping"})

    doc = item_docs(products, SUPPLIERS)[0]

    assert doc["is_stock_item"] == 0
    assert "item_defaults" not in doc


def test_item_docs_shorten_long_names_but_keep_full_description():
    long_description = "X" * 200

    doc = item_docs(make_products({"description": long_description}), SUPPLIERS)[0]

    assert len(doc["item_name"]) == MAX_ITEM_NAME_LENGTH
    assert doc["description"] == long_description


def test_customer_docs_make_wholesale_customers_companies():
    customers = pd.DataFrame(
        {
            "customer": ["17850", "12346"],
            "country": ["United Kingdom", "France"],
            "segment": ["Wholesale", "Retail"],
        }
    )

    docs = customer_docs(customers)

    assert [doc["customer_type"] for doc in docs] == ["Company", "Individual"]
    assert docs[1]["territory"] == "France"
    assert docs[1]["customer_group"] == "Retail"


def test_territory_docs_list_each_invoice_country_once():
    df = pd.DataFrame({"country": ["France", "United Kingdom", "France"]})

    names = [doc["territory_name"] for doc in territory_docs(df)]

    assert names == ["France", "United Kingdom"]


def test_supplier_docs_list_shared_suppliers_once():
    suppliers = {"Party & Gift Wrap": "Paper & Ribbon Ltd", "Stationery": "Paper & Ribbon Ltd"}

    assert [doc["supplier_name"] for doc in supplier_docs(suppliers)] == ["Paper & Ribbon Ltd"]


def test_every_category_has_a_supplier():
    categories, _ = load_categories()
    suppliers = load_suppliers()

    assert {category.name for category in categories} | {OTHER} == set(suppliers)
