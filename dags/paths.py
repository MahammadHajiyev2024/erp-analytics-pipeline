"""Plain, Airflow-free helpers shared by dags/erp_pipeline.py.

Kept separate from the DAG file (which imports airflow.sdk at module scope, and so can't be
imported by pytest without Airflow installed -- see docs/airflow-setup.md) so the actual source
list and path logic stay unit-testable like the rest of the codebase.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from extractors.erpnext.customer import extract_customers
from extractors.erpnext.item import extract_items
from extractors.erpnext.purchase_invoice import run_purchase_invoice_extraction
from extractors.erpnext.sales_invoice import run_sales_invoice_extraction
from extractors.erpnext.stock_ledger_entry import extract_stock_ledger_entries
from extractors.erpnext.supplier import extract_suppliers
from extractors.fred.exchange_rates import extract_exchange_rates
from loaders import (
    load_customers_to_bronze,
    load_fred_exchange_rates_to_bronze,
    load_items_to_bronze,
    load_purchase_invoices_to_bronze,
    load_sales_invoices_to_bronze,
    load_stock_ledger_entries_to_bronze,
    load_suppliers_to_bronze,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VOLUME = "/Volumes/erp_analytics/bronze/landing"

ExtractFn = Callable[..., Path | None]
LoadFn = Callable[[str], int]

# The same (folder, extract, load) mapping data/scratch/run_incremental.py uses -- re-declared
# here because that script is gitignored and not importable by the DAG.
SOURCES: list[tuple[str, ExtractFn, LoadFn]] = [
    ("customer", extract_customers, load_customers_to_bronze),
    ("item", extract_items, load_items_to_bronze),
    ("supplier", extract_suppliers, load_suppliers_to_bronze),
    ("sales_invoice", run_sales_invoice_extraction, load_sales_invoices_to_bronze),
    ("purchase_invoice", run_purchase_invoice_extraction, load_purchase_invoices_to_bronze),
    ("stock_ledger_entry", extract_stock_ledger_entries, load_stock_ledger_entries_to_bronze),
    ("fred_exchange_rates", extract_exchange_rates, load_fred_exchange_rates_to_bronze),
]


def extract_kwargs(folder: str) -> dict[str, Path]:
    """Absolute output_dir/watermark_path for one source, independent of the process's CWD."""
    return {
        "output_dir": PROJECT_ROOT / "data" / "landing" / folder,
        "watermark_path": PROJECT_ROOT / "data" / "watermarks.json",
    }
