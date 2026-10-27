"""Extract Stock Ledger Entries (list-only, all fields) to the landing folder."""

from pathlib import Path

from extractors.erpnext.listing import cli, run_list_extraction

DOCTYPE = "Stock Ledger Entry"


def extract_stock_ledger_entries(**kwargs) -> Path | None:
    """Extract Stock Ledger Entries modified since the watermark; see run_list_extraction."""
    return run_list_extraction(DOCTYPE, **kwargs)


if __name__ == "__main__":
    cli(DOCTYPE)
