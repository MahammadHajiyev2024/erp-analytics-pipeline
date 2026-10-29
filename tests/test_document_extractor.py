"""Tests for the generic document extractor: listing, overlap, watermark, one GET each."""

import json
from datetime import UTC, datetime

import pytest

from common.erpnext import ERPNextError
from extractors.erpnext import documents, purchase_invoice, sales_invoice
from extractors.watermark import get_watermark, update_watermark

DOCTYPE = "Sales Invoice"


class FakeResponse:
    ok = True

    def __init__(self, data):
        self._data = data

    def json(self):
        return {"data": self._data}


class FakeSession:
    """Serves the list API (filter, sort, limit) and single documents with child tables."""

    def __init__(self, rows, fetched_modified=None):
        self.rows = rows
        self.fetched_modified = fetched_modified or {}
        self.list_calls = []
        self.fetched = []

    def get(self, url, params=None, timeout=None):
        path = url.split("/api/resource/", 1)[1]
        if "/" in path:
            return self._document(path.split("/", 1)[1])
        self.list_calls.append(params)
        rows = self.rows
        for _, field, op, value in json.loads(params.get("filters", "[]")):
            rows = [r for r in rows if r[field] >= value and (op == ">=" or r[field] != value)]
        order = params["order_by"]
        if order == "name asc":
            rows = sorted(rows, key=lambda r: r["name"])
        else:
            rows = sorted(rows, key=lambda r: (r["modified"], r["name"]), reverse="desc" in order)
        start, size = params["limit_start"], params["limit_page_length"]
        fields = json.loads(params["fields"])
        return FakeResponse([{f: r[f] for f in fields} for r in rows[start : start + size]])

    def _document(self, name):
        self.fetched.append(name)
        row = next((r for r in self.rows if r["name"] == name), None)
        if row is None or row.get("empty"):
            return FakeResponse({})
        modified = self.fetched_modified.get(name, row["modified"])
        return FakeResponse({**row, "modified": modified, "items": [{"item_code": "X"}]})


def row(name, modified):
    return {"name": name, "modified": modified}


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Return a function that runs the extraction against a FakeSession."""
    monkeypatch.setattr(documents, "load_dotenv", lambda: None)
    monkeypatch.setenv("ERPNEXT_API_KEY", "key")
    monkeypatch.setenv("ERPNEXT_API_SECRET", "secret")
    state_file = tmp_path / "watermarks.json"
    output_dir = tmp_path / "landing"

    def _run(session, **kwargs):
        monkeypatch.setattr(documents, "get_session", lambda key, secret: session)
        return documents.run_document_extraction(
            DOCTYPE, output_dir=output_dir, watermark_path=state_file, **kwargs
        )

    _run.state_file = state_file
    _run.output_dir = output_dir
    return _run


def set_watermark(state_file, modified):
    now = datetime.now(UTC).isoformat()
    update_watermark(DOCTYPE, modified, 1, now, state_file=state_file)


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_full_load_fetches_every_document_with_child_tables(run):
    session = FakeSession(
        [row("b", "2026-01-01 11:00:00.000000"), row("a", "2026-01-01 12:00:00.000000")]
    )

    path = run(session)

    lines = read_lines(path)
    assert [line["name"] for line in lines] == ["a", "b"]
    assert lines[0]["items"] == [{"item_code": "X"}]
    assert lines[0]["_source"] == "erpnext/sales_invoice"
    assert all(call["order_by"] in {"modified desc", "name asc"} for call in session.list_calls)
    assert get_watermark(DOCTYPE, state_file=run.state_file) == "2026-01-01 12:00:00.000000"
    assert not list(run.output_dir.glob("*.part"))


def test_watermark_comes_from_the_list_not_the_fetched_documents(run):
    set_watermark(run.state_file, "2026-01-01 10:00:00.000000")
    # "a" is paid while the run fetches documents: its fetched modified is newer than listed
    session = FakeSession(
        [row("a", "2026-01-01 10:30:00.000000")],
        fetched_modified={"a": "2026-01-01 15:00:00.000000"},
    )

    path = run(session)

    assert read_lines(path)[0]["modified"] == "2026-01-01 15:00:00.000000"
    assert get_watermark(DOCTYPE, state_file=run.state_file) == "2026-01-01 10:30:00.000000"


def test_incremental_run_rereads_overlap_and_adds_new_documents(run):
    set_watermark(run.state_file, "2026-01-01 10:00:00.000000")
    session = FakeSession(
        [
            row("old", "2026-01-01 07:00:00.000000"),  # before the overlap: not read
            row("a", "2026-01-01 09:50:00.000000"),  # inside the overlap: read again
            row("new", "2026-01-01 10:05:00.000000"),
        ]
    )

    path = run(session)

    assert [line["name"] for line in read_lines(path)] == ["a", "new"]
    assert session.fetched == ["a", "new"]
    assert get_watermark(DOCTYPE, state_file=run.state_file) == "2026-01-01 10:05:00.000000"


def test_overlap_only_run_fetches_nothing_and_returns_none(run):
    set_watermark(run.state_file, "2026-01-01 10:00:00.000000")
    session = FakeSession([row("a", "2026-01-01 09:50:00.000000")])

    assert run(session) is None
    assert session.fetched == []
    assert not run.output_dir.exists() or not list(run.output_dir.iterdir())


def test_truncated_full_load_keeps_file_but_sets_no_watermark(run):
    session = FakeSession([row(n, "2026-01-01 10:00:00.000000") for n in "abc"])

    path = run(session, max_records=2)

    assert len(read_lines(path)) == 2
    assert get_watermark(DOCTYPE, state_file=run.state_file) is None


def test_empty_document_raises_and_leaves_watermark_and_landing_unchanged(run):
    set_watermark(run.state_file, "2026-01-01 10:00:00.000000")
    session = FakeSession([{**row("a", "2026-01-01 10:05:00.000000"), "empty": True}])

    with pytest.raises(ERPNextError, match="Empty document"):
        run(session)

    assert get_watermark(DOCTYPE, state_file=run.state_file) == "2026-01-01 10:00:00.000000"
    assert not list(run.output_dir.glob("*.jsonl"))


@pytest.mark.parametrize(
    ("module", "function", "doctype"),
    [
        (sales_invoice, "run_sales_invoice_extraction", "Sales Invoice"),
        (purchase_invoice, "run_purchase_invoice_extraction", "Purchase Invoice"),
    ],
)
def test_wrappers_extract_their_own_doctype(monkeypatch, module, function, doctype):
    calls = []
    monkeypatch.setattr(
        module, "run_document_extraction", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    getattr(module, function)()

    assert calls[0][0][0] == doctype
