"""Unit tests for dags/paths.py.

dags/erp_pipeline.py imports airflow.sdk at module scope and so can't be imported here (Airflow
is deliberately never installed outside its own Docker image -- see docs/airflow-setup.md). This
module holds the real logic (the source list, path construction) precisely so it stays testable.
"""

from pathlib import Path

from dags.paths import PROJECT_ROOT, SOURCES, extract_kwargs
from extractors.erpnext.customer import extract_customers
from extractors.erpnext.item import extract_items
from extractors.erpnext.purchase_invoice import run_purchase_invoice_extraction
from extractors.erpnext.sales_invoice import run_sales_invoice_extraction
from extractors.erpnext.stock_ledger_entry import extract_stock_ledger_entries
from extractors.fred.exchange_rates import extract_exchange_rates
from loaders import (
    load_customers_to_bronze,
    load_fred_exchange_rates_to_bronze,
    load_items_to_bronze,
    load_purchase_invoices_to_bronze,
    load_sales_invoices_to_bronze,
    load_stock_ledger_entries_to_bronze,
)

EXPECTED_SOURCES = {
    "customer": (extract_customers, load_customers_to_bronze),
    "item": (extract_items, load_items_to_bronze),
    "sales_invoice": (run_sales_invoice_extraction, load_sales_invoices_to_bronze),
    "purchase_invoice": (run_purchase_invoice_extraction, load_purchase_invoices_to_bronze),
    "stock_ledger_entry": (extract_stock_ledger_entries, load_stock_ledger_entries_to_bronze),
    "fred_exchange_rates": (extract_exchange_rates, load_fred_exchange_rates_to_bronze),
}


def test_sources_has_exactly_the_expected_six_folders() -> None:
    """Catches a typo'd or missing source before it silently drops out of the DAG."""
    folders = [folder for folder, _, _ in SOURCES]
    assert sorted(folders) == sorted(EXPECTED_SOURCES)


def test_sources_has_no_duplicate_folder_names() -> None:
    folders = [folder for folder, _, _ in SOURCES]
    assert len(folders) == len(set(folders))


def test_sources_functions_match_the_real_imported_functions() -> None:
    """Catches a copy-paste mistake pairing the wrong extract/load function to a folder."""
    for folder, extract_fn, load_fn in SOURCES:
        expected_extract, expected_load = EXPECTED_SOURCES[folder]
        assert extract_fn is expected_extract, f"{folder}: wrong extract function"
        assert load_fn is expected_load, f"{folder}: wrong load function"


def test_extract_kwargs_returns_absolute_paths_rooted_at_project_root() -> None:
    kwargs = extract_kwargs("customer")
    assert kwargs["output_dir"] == PROJECT_ROOT / "data" / "landing" / "customer"
    assert kwargs["watermark_path"] == PROJECT_ROOT / "data" / "watermarks.json"
    assert kwargs["output_dir"].is_absolute()
    assert kwargs["watermark_path"].is_absolute()


def test_extract_kwargs_uses_a_distinct_output_dir_per_folder() -> None:
    assert extract_kwargs("customer")["output_dir"] != extract_kwargs("item")["output_dir"]


def test_project_root_is_the_repository_root() -> None:
    assert Path(__file__).resolve().parent.parent == PROJECT_ROOT
