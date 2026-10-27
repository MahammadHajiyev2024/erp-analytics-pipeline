"""Extract Stock Ledger Entries (list-only, all fields) to the landing folder."""

import argparse
import logging
from pathlib import Path

from extractors.erpnext.listing import run_list_extraction
from extractors.watermark import DEFAULT_STATE_FILE

DOCTYPE = "Stock Ledger Entry"


def extract_stock_ledger_entries(**kwargs) -> Path | None:
    """Extract Stock Ledger Entries modified since the watermark; see run_list_extraction."""
    return run_list_extraction(DOCTYPE, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-records", type=int, help="stop after this many records (trial)")
    parser.add_argument("--output-dir", type=Path, help="default: data/landing/stock_ledger_entry")
    parser.add_argument("--watermark-path", type=Path, default=DEFAULT_STATE_FILE)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = extract_stock_ledger_entries(
        output_dir=args.output_dir,
        watermark_path=args.watermark_path,
        max_records=args.max_records,
    )
    print(path)


if __name__ == "__main__":
    main()
