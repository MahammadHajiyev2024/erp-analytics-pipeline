"""Tests for the Sales Invoice extractor (all ERPNext calls mocked)."""

import copy
import json

import pytest

from common.erpnext import ERPNextError
from extractors.erpnext import sales_invoice
from extractors.watermark import get_watermark

DOCS = {
    "SINV-0001": {
        "name": "SINV-0001",
        "modified": "2026-10-24 10:00:00.000000",
        "docstatus": 1,
        "items": [{"item_code": "A", "qty": 2}, {"item_code": "B", "qty": 1}],
        "taxes": [{"account_head": "VAT - MHG", "rate": 20}],
    },
    "SINV-0002": {
        "name": "SINV-0002",
        "modified": "2026-10-24 11:00:00.000000",
        "docstatus": 2,
        "items": [{"item_code": "C", "qty": 5}],
        "taxes": [],
    },
}


@pytest.fixture
def docs(monkeypatch):
    """Mock ERPNext: two invoices, served from a dict tests can change."""
    served = copy.deepcopy(DOCS)
    monkeypatch.setenv("ERPNEXT_API_KEY", "test-key")
    monkeypatch.setenv("ERPNEXT_API_SECRET", "test-secret")
    monkeypatch.setattr(sales_invoice, "get_session", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        sales_invoice, "fetch_sales_invoice_names", lambda *args, **kwargs: list(served)
    )
    monkeypatch.setattr(
        sales_invoice,
        "fetch_sales_invoice_doc",
        lambda session, base_url, name: copy.deepcopy(served[name]),
    )
    return served


def test_child_tables_are_written_as_lists(docs, tmp_path):
    path = sales_invoice.run_sales_invoice_extraction(
        output_dir=tmp_path / "landing", watermark_path=tmp_path / "watermarks.json"
    )

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    first = records[0]
    assert isinstance(first["items"], list) and len(first["items"]) == 2
    assert isinstance(first["taxes"], list) and len(first["taxes"]) == 1
    assert first["items"][0]["item_code"] == "A"
    assert first["_source"] == "erpnext/sales_invoice"
    assert records[1]["docstatus"] == 2


def test_empty_document_fails_without_file_or_watermark(docs, tmp_path):
    docs["SINV-0002"] = {}
    landing = tmp_path / "landing"
    state = tmp_path / "watermarks.json"

    with pytest.raises(ERPNextError, match="SINV-0002"):
        sales_invoice.run_sales_invoice_extraction(output_dir=landing, watermark_path=state)

    assert list(landing.glob("*.jsonl")) == []
    assert get_watermark("Sales Invoice", state_file=state) is None
