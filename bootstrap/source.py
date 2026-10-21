"""Read the UCI Online Retail II source data."""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RAW_PATH = DATA_DIR / "raw" / "online_retail_II.xlsx"
CACHE_PATH = DATA_DIR / "interim" / "online_retail.parquet"

TEXT_COLUMNS = ["Invoice", "StockCode", "Description", "Country"]

COLUMN_NAMES = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "price",
    "Customer ID": "customer_id",
    "Country": "country",
}


def read_raw(path: Path) -> pd.DataFrame:
    """Read every sheet of the source workbook into one DataFrame."""
    text_types = {column: "string" for column in TEXT_COLUMNS}
    sheets = pd.read_excel(path, sheet_name=None, dtype=text_types)
    df = pd.concat(sheets.values(), ignore_index=True)
    df["Customer ID"] = df["Customer ID"].astype("Int64")
    return df


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename the source columns to snake_case and trim spaces around stock codes."""
    df = df.rename(columns=COLUMN_NAMES)
    return df.assign(stock_code=df["stock_code"].str.strip())


def load_source(raw_path: Path = RAW_PATH, cache_path: Path = CACHE_PATH) -> pd.DataFrame:
    """Return the source data, reading the workbook only when no cached copy exists."""
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
    else:
        df = read_raw(raw_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
    return standardize(df)


def main() -> None:
    """Load the source data and print its size and column types."""
    df = load_source()
    print(f"Rows: {len(df):,}")
    print(df.dtypes)


if __name__ == "__main__":
    main()
