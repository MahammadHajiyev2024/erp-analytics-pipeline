"""Extract customers (list-only, all fields) to the landing folder."""

from pathlib import Path

from extractors.erpnext.listing import cli, run_list_extraction

DOCTYPE = "Customer"


def extract_customers(**kwargs) -> Path | None:
    """Extract customers modified since the watermark; see run_list_extraction."""
    return run_list_extraction(DOCTYPE, **kwargs)


if __name__ == "__main__":
    cli(DOCTYPE)
