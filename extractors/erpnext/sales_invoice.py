"""Extractor for ERPNext Sales Invoice (header plus items and taxes)."""

import logging
from pathlib import Path

from extractors.erpnext.documents import run_document_extraction
from extractors.watermark import DEFAULT_STATE_FILE

DOCTYPE = "Sales Invoice"


def run_sales_invoice_extraction(
    output_dir: Path | None = None,
    watermark_path: Path = DEFAULT_STATE_FILE,
    max_records: int | None = None,
) -> Path | None:
    """Extract Sales Invoices modified since the watermark."""
    return run_document_extraction(
        DOCTYPE, output_dir=output_dir, watermark_path=watermark_path, max_records=max_records
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Staged file:", run_sales_invoice_extraction())
