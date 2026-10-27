"""Tests for the generic list-only extractor: keyset pagination, overlap, watermark."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from common.erpnext import ERPNextError
from extractors.erpnext import listing
from extractors.watermark import get_watermark, update_watermark

DOCTYPE = "Stock Ledger Entry"


class FakeResponse:
    ok = True

    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return {"data": self._rows}


class FakeSession:
    """Serves rows like ERPNext's list API: filter, sort, then limit."""

    def __init__(self, rows, after_call=None):
        self.rows = rows
        self.after_call = after_call
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(params)
        rows = self.rows
        for _, field, op, value in json.loads(params.get("filters", "[]")):
            assert (field, op) in {("modified", ">="), ("name", ">")}
            rows = [r for r in rows if r[field] >= value and (op == ">=" or r[field] != value)]
        order = params["order_by"]
        assert order in {"modified asc, name asc", "modified desc", "name asc"}
        if order == "name asc":
            rows = sorted(rows, key=lambda r: r["name"])
        else:
            rows = sorted(rows, key=lambda r: (r["modified"], r["name"]), reverse="desc" in order)
        start, size = params["limit_start"], params["limit_page_length"]
        page = [dict(r) for r in rows[start : start + size]]
        if self.after_call:
            self.after_call(self, len(self.calls))
        return FakeResponse(page)


def row(name, modified):
    return {"name": name, "modified": modified}


def names(records):
    return [r["name"] for r in records]


def test_keyset_pages_return_every_row_once():
    rows = [
        row("a", "2026-01-01 00:00:01"),
        row("b", "2026-01-01 00:00:02"),
        row("c", "2026-01-01 00:00:02"),
        row("d", "2026-01-01 00:00:03"),
        row("e", "2026-01-01 00:00:04"),
    ]
    session = FakeSession(rows)

    got = names(listing.iter_records(session, "http://erp", DOCTYPE, page_size=3))

    assert got == ["a", "b", "c", "d", "e"]
    assert all(call["limit_start"] == 0 for call in session.calls)


def test_rows_updated_during_the_run_are_not_skipped():
    rows = [row(n, f"2026-01-01 00:00:0{i}") for i, n in enumerate("abcde", start=1)]

    def update_after_first_page(session, call_count):
        if call_count == 1:  # a was read, c not yet; both move to the end
            session.rows[0]["modified"] = "2026-01-01 00:00:09"
            session.rows[2]["modified"] = "2026-01-01 00:00:08"

    session = FakeSession(rows, after_call=update_after_first_page)

    got = names(listing.iter_records(session, "http://erp", DOCTYPE, page_size=2))

    assert set(got) == {"a", "b", "c", "d", "e"}
    assert got.count("a") == 2  # re-read with its new modified; silver keeps the latest


def test_page_of_identical_modified_values_raises():
    rows = [row(n, "2026-01-01 00:00:01") for n in "xyz"]

    with pytest.raises(ERPNextError, match="share modified"):
        list(listing.iter_records(FakeSession(rows), "http://erp", DOCTYPE, page_size=2))


def test_full_load_pages_by_name():
    rows = [row(n, f"2026-01-01 00:00:0{9 - i}") for i, n in enumerate("abcde")]
    session = FakeSession(rows)

    got = names(listing.iter_records_by_name(session, "http://erp", DOCTYPE, page_size=2))

    assert got == ["a", "b", "c", "d", "e"]
    assert all(call["order_by"] == "name asc" for call in session.calls)


def test_overlap_start():
    half_hour = timedelta(minutes=30)
    assert listing.overlap_start(None) is None
    assert listing.overlap_start("2026-10-25 06:32:35.297497") == "2026-10-25 04:32:35.297497"
    assert listing.overlap_start("2026-10-25 06:32:35", half_hour) == "2026-10-25 06:02:35.000000"


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Return a function that runs the extraction against a FakeSession with given rows."""
    monkeypatch.setattr(listing, "load_dotenv", lambda: None)
    monkeypatch.setenv("ERPNEXT_API_KEY", "key")
    monkeypatch.setenv("ERPNEXT_API_SECRET", "secret")
    state_file = tmp_path / "watermarks.json"
    output_dir = tmp_path / "landing"

    def _run(rows, **kwargs):
        monkeypatch.setattr(listing, "get_session", lambda key, secret: FakeSession(rows))
        return listing.run_list_extraction(
            DOCTYPE, output_dir=output_dir, watermark_path=state_file, **kwargs
        )

    _run.state_file = state_file
    _run.output_dir = output_dir
    return _run


def set_watermark(state_file, modified):
    now = datetime.now(UTC).isoformat()
    update_watermark(DOCTYPE, modified, 1, now, state_file=state_file)


def test_first_run_writes_all_rows_and_moves_watermark(run):
    rows = [row("a", "2026-01-01 10:00:00.000000"), row("b", "2026-01-01 11:00:00.000000")]

    path = run(rows)

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert names(lines) == ["a", "b"]
    assert lines[0]["_source"] == "erpnext/stock_ledger_entry"
    assert len({line["_batch_id"] for line in lines}) == 1
    assert get_watermark(DOCTYPE, state_file=run.state_file) == "2026-01-01 11:00:00.000000"
    assert not list(run.output_dir.glob("*.part"))


def test_truncated_full_load_does_not_set_watermark(run):
    rows = [row(n, "2026-01-01 10:00:00.000000") for n in "abc"]

    path = run(rows, max_records=2)

    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert get_watermark(DOCTYPE, state_file=run.state_file) is None


def test_run_with_only_overlap_rows_returns_none(run):
    set_watermark(run.state_file, "2026-01-01 10:00:00.000000")
    rows = [row("a", "2026-01-01 09:50:00.000000"), row("b", "2026-01-01 10:00:00.000000")]

    assert run(rows) is None
    assert not list(run.output_dir.iterdir())
    assert get_watermark(DOCTYPE, state_file=run.state_file) == "2026-01-01 10:00:00.000000"


def test_incremental_run_rereads_overlap_and_adds_new_rows(run):
    set_watermark(run.state_file, "2026-01-01 10:00:00.000000")
    rows = [
        row("old", "2026-01-01 07:00:00.000000"),  # before the overlap: not read
        row("a", "2026-01-01 09:50:00.000000"),  # inside the overlap: read again
        row("new", "2026-01-01 10:05:00.000000"),
    ]

    path = run(rows)

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert names(lines) == ["a", "new"]
    assert get_watermark(DOCTYPE, state_file=run.state_file) == "2026-01-01 10:05:00.000000"
