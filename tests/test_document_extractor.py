"""Tests for the generic ERPNext document extractor (all ERPNext calls mocked)."""

import copy
import json
from unittest.mock import MagicMock

import pytest

from common.erpnext import ERPNextError
from extractors.erpnext import documents, purchase_invoice, sales_invoice
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
    """Mock ERPNext: two documents, served from a dict tests can change."""
    served = copy.deepcopy(DOCS)
    monkeypatch.setenv("ERPNEXT_API_KEY", "test-key")
    monkeypatch.setenv("ERPNEXT_API_SECRET", "test-secret")
    monkeypatch.setattr(documents, "get_session", lambda *args, **kwargs: object())
    monkeypatch.setattr(documents, "fetch_document_names", lambda *args, **kwargs: list(served))
    monkeypatch.setattr(
        documents,
        "fetch_document",
        lambda session, base_url, doctype, name: copy.deepcopy(served[name]),
    )
    return served


def test_child_tables_are_written_as_lists(docs, tmp_path):
    state = tmp_path / "watermarks.json"
    path = documents.run_document_extraction(
        "Sales Invoice", output_dir=tmp_path / "landing", watermark_path=state
    )

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert path.name.startswith("sales_invoice_")
    assert len(records) == 2
    assert isinstance(records[0]["items"], list) and len(records[0]["items"]) == 2
    assert isinstance(records[0]["taxes"], list) and len(records[0]["taxes"]) == 1
    assert records[0]["_source"] == "erpnext/sales_invoice"
    assert records[1]["docstatus"] == 2
    assert get_watermark("Sales Invoice", state_file=state) == "2026-10-24 11:00:00.000000"


def test_empty_document_fails_without_file_or_watermark(docs, tmp_path):
    docs["SINV-0002"] = {}
    landing = tmp_path / "landing"
    state = tmp_path / "watermarks.json"

    with pytest.raises(ERPNextError, match="SINV-0002"):
        documents.run_document_extraction("Sales Invoice", output_dir=landing, watermark_path=state)

    assert list(landing.glob("*.jsonl")) == []
    assert get_watermark("Sales Invoice", state_file=state) is None


def test_names_are_listed_for_the_doctype_after_the_watermark():
    session = MagicMock()
    page = MagicMock(ok=True)
    page.json.return_value = {"data": [{"name": "PINV-1", "modified": "2026-10-02"}]}
    session.get.return_value = page

    names = documents.fetch_document_names(
        session, "http://erp", "Purchase Invoice", watermark="2026-10-01 00:00:00"
    )

    assert names == ["PINV-1"]
    assert session.get.call_args.args[0] == "http://erp/api/resource/Purchase Invoice"
    filters = json.loads(session.get.call_args.kwargs["params"]["filters"])
    assert filters == [["Purchase Invoice", "modified", ">", "2026-10-01 00:00:00"]]


@pytest.mark.parametrize(
    ("module", "function", "doctype"),
    [
        (sales_invoice, "run_sales_invoice_extraction", "Sales Invoice"),
        (purchase_invoice, "run_purchase_invoice_extraction", "Purchase Invoice"),
    ],
)
def test_wrappers_extract_their_own_doctype(monkeypatch, module, function, doctype):
    calls = []
    monkeypatch.setattr(module, "run_document_extraction", lambda *args: calls.append(args))

    getattr(module, function)()

    assert calls[0][0] == doctype
