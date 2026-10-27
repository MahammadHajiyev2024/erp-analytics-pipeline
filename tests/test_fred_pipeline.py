"""Tests for the FRED exchange rate extractor and its bronze loader."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from extractors.fred import exchange_rates as fred
from extractors.watermark import get_watermark, update_watermark
from loaders.bronze import load_fred_exchange_rates_to_bronze

KEY = "FRED DEXUSUK"


class FakeResponse:
    def __init__(self, observations, count=None, status=200):
        self.status_code = status
        self.ok = status == 200
        self.text = "error"
        self._body = {
            "count": len(observations) if count is None else count,
            "observations": observations,
        }

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.params = None

    def get(self, url, params, timeout):
        self.params = params
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def obs(day, value="1.3000"):
    return {
        "realtime_start": "2026-10-27",
        "realtime_end": "2026-10-27",
        "date": day,
        "value": value,
    }


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Return a function that runs the extraction against a FakeSession."""
    monkeypatch.setattr(fred, "load_dotenv", lambda: None)
    monkeypatch.setenv("FRED_API_KEY", "SECRETKEY")
    state_file = tmp_path / "watermarks.json"
    output_dir = tmp_path / "landing"

    def _run(response):
        session = FakeSession(response)
        monkeypatch.setattr(fred, "get_session", lambda: session)
        _run.session = session
        return fred.extract_exchange_rates(output_dir=output_dir, watermark_path=state_file)

    _run.state_file = state_file
    _run.output_dir = output_dir
    return _run


def test_redact_hides_api_key():
    text = "url: /fred/series/observations?series_id=DEXUSUK&api_key=abc123&file_type=json"
    assert fred.redact(text) == (
        "url: /fred/series/observations?series_id=DEXUSUK&api_key=***&file_type=json"
    )


def test_connection_error_does_not_leak_key(run):
    error = requests.ConnectionError("Max retries exceeded with url: /x?api_key=SECRETKEY&a=1")

    with pytest.raises(fred.FREDError) as raised:
        run(error)

    assert "SECRETKEY" not in str(raised.value)
    assert raised.value.__suppress_context__  # original exception (with the URL) not shown


def test_first_run_starts_at_start_date_and_sets_watermark(run):
    path = run(FakeResponse([obs("2023-11-01"), obs("2023-11-02", ".")]))

    assert run.session.params["observation_start"] == "2023-11-01"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [line["date"] for line in lines] == ["2023-11-01", "2023-11-02"]
    assert lines[1]["value"] == "."  # holidays kept as received
    assert lines[0]["series_id"] == "DEXUSUK"
    assert lines[0]["_source"] == "fred/dexusuk"
    assert get_watermark(KEY, state_file=run.state_file) == "2023-11-02"
    assert not list(run.output_dir.glob("*.part"))


def test_incremental_run_starts_overlap_before_watermark(run):
    update_watermark(KEY, "2026-10-16", 1, "2026-10-20T00:00:00+00:00", state_file=run.state_file)

    path = run(FakeResponse([obs("2026-10-15"), obs("2026-10-16"), obs("2026-10-23")]))

    assert run.session.params["observation_start"] == "2026-09-16"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3
    assert get_watermark(KEY, state_file=run.state_file) == "2026-10-23"


def test_run_without_new_dates_returns_none(run):
    update_watermark(KEY, "2026-10-16", 1, "2026-10-20T00:00:00+00:00", state_file=run.state_file)

    assert run(FakeResponse([obs("2026-10-15"), obs("2026-10-16")])) is None
    assert not run.output_dir.exists() or not list(run.output_dir.iterdir())


def test_more_observations_than_returned_raises(run):
    with pytest.raises(fred.FREDError, match="paging"):
        run(FakeResponse([obs("2023-11-01")], count=5))


@patch("loaders.bronze.get_connection")
def test_fred_loader_uses_fred_key_columns(mock_get_conn: MagicMock) -> None:
    cursor = mock_get_conn.return_value.__enter__.return_value.cursor.return_value.__enter__
    cursor.return_value.fetchone.return_value = (1, 750)

    inserted = load_fred_exchange_rates_to_bronze("/Volumes/x/fred_exchange_rates/f.jsonl")

    ddl, copy_into = (c.args[0] for c in cursor.return_value.execute.call_args_list)
    assert inserted == 750
    assert "bronze.fred_exchange_rates" in ddl
    assert "observation_date STRING" in ddl and "docstatus" not in ddl
    assert "get_json_object(value, '$.date') AS observation_date" in copy_into
