import pandas as pd

from bootstrap.source import load_source, read_raw, standardize_columns


def make_sheet(invoice: str, customer_id: float | None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Invoice": [invoice],
            "StockCode": ["85123A"],
            "Description": ["WHITE HANGING HEART T-LIGHT HOLDER"],
            "Quantity": [6],
            "InvoiceDate": [pd.Timestamp("2010-12-01 08:26")],
            "Price": [2.55],
            "Customer ID": [customer_id],
            "Country": ["United Kingdom"],
        }
    )


def write_workbook(path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path) as writer:
        for name, sheet in sheets.items():
            sheet.to_excel(writer, sheet_name=name, index=False)


def test_read_raw_combines_all_sheets(tmp_path):
    path = tmp_path / "source.xlsx"
    write_workbook(path, {"2009": make_sheet("489434", 13085), "2010": make_sheet("C536379", None)})

    df = read_raw(path)

    assert df["Invoice"].tolist() == ["489434", "C536379"]


def test_read_raw_keeps_codes_as_text(tmp_path):
    path = tmp_path / "source.xlsx"
    write_workbook(path, {"2010": make_sheet("536365", 17850)})

    df = read_raw(path)

    assert df["Invoice"].dtype == "string"
    assert df["StockCode"].iloc[0] == "85123A"


def test_read_raw_keeps_missing_customer_ids(tmp_path):
    path = tmp_path / "source.xlsx"
    write_workbook(path, {"2010": pd.concat([make_sheet("1", 17850), make_sheet("2", None)])})

    df = read_raw(path)

    assert df["Customer ID"].dtype == "Int64"
    assert df["Customer ID"].isna().tolist() == [False, True]


def test_standardize_columns_uses_snake_case():
    df = standardize_columns(make_sheet("536365", 17850))

    assert list(df.columns) == [
        "invoice",
        "stock_code",
        "description",
        "quantity",
        "invoice_date",
        "price",
        "customer_id",
        "country",
    ]


def test_load_source_reads_cache_without_workbook(tmp_path):
    cache_path = tmp_path / "source.parquet"
    make_sheet("536365", 17850).to_parquet(cache_path, index=False)

    df = load_source(raw_path=tmp_path / "missing.xlsx", cache_path=cache_path)

    assert df["invoice"].tolist() == ["536365"]


def test_load_source_creates_cache_from_workbook(tmp_path):
    raw_path = tmp_path / "source.xlsx"
    cache_path = tmp_path / "interim" / "source.parquet"
    write_workbook(raw_path, {"2010": make_sheet("536365", 17850)})

    load_source(raw_path=raw_path, cache_path=cache_path)

    assert cache_path.exists()
