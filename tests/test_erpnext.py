import json
from unittest.mock import Mock

import pytest
import requests

import common.erpnext
from common.erpnext import (
    MAX_ATTEMPTS,
    PAGE_SIZE,
    TIMEOUT_SECONDS,
    ERPNextError,
    can_read,
    create_missing,
    get_logged_user,
    get_session,
    insert,
    list_names,
    list_values,
)

BASE_URL = "http://erpnext.test"


def test_get_session_sends_api_token():
    session = get_session("key", "secret")

    assert session.headers["Authorization"] == "token key:secret"


def test_get_logged_user_returns_user_name():
    session = Mock()
    session.get.return_value.json.return_value = {"message": "pipeline@mhg.local"}

    assert get_logged_user(session, BASE_URL) == "pipeline@mhg.local"
    session.get.assert_called_once_with(
        f"{BASE_URL}/api/method/frappe.auth.get_logged_user",
        timeout=TIMEOUT_SECONDS,
    )


def test_get_logged_user_raises_on_rejected_credentials():
    session = Mock()
    session.get.return_value.raise_for_status.side_effect = requests.HTTPError("401")

    with pytest.raises(requests.HTTPError):
        get_logged_user(session, BASE_URL)


@pytest.mark.parametrize(("response_ok", "expected"), [(True, True), (False, False)])
def test_can_read_follows_response_status(response_ok, expected):
    session = Mock()
    session.get.return_value.ok = response_ok

    assert can_read(session, BASE_URL, "Customer") is expected


def fake_response(ok: bool = True, body: dict | None = None) -> Mock:
    response = Mock()
    response.ok = ok
    response.json.return_value = body or {}
    return response


def names_page(*names: str, field: str = "name") -> Mock:
    return fake_response(body={"data": [{field: name} for name in names]})


def test_list_names_fetches_every_page():
    full_page = [f"ITEM{number}" for number in range(PAGE_SIZE)]
    session = Mock()
    session.get.side_effect = [names_page(*full_page), names_page("LAST")]

    names = list_names(session, BASE_URL, "Item")

    assert len(names) == PAGE_SIZE + 1
    assert session.get.call_count == 2


def test_list_names_raises_with_erpnext_explanation():
    session = Mock()
    session.get.return_value = fake_response(ok=False, body={"exception": "No permission"})

    with pytest.raises(ERPNextError, match="No permission"):
        list_names(session, BASE_URL, "Item")


def test_insert_posts_document_and_returns_stored_version():
    session = Mock()
    session.post.return_value = fake_response(body={"data": {"name": "Christmas"}})

    stored = insert(session, BASE_URL, "Item Group", {"item_group_name": "Christmas"})

    assert stored == {"name": "Christmas"}
    session.post.assert_called_once_with(
        f"{BASE_URL}/api/resource/Item Group",
        json={"item_group_name": "Christmas"},
        timeout=TIMEOUT_SECONDS,
    )


def test_insert_raises_with_erpnext_explanation():
    session = Mock()
    session.post.return_value = fake_response(
        ok=False, body={"exception": "LinkValidationError: Could not find Territory: France"}
    )

    with pytest.raises(ERPNextError, match="Could not find Territory"):
        insert(session, BASE_URL, "Customer", {"customer_name": "17850"})


def test_create_missing_creates_only_new_documents():
    session = Mock()
    session.get.return_value = names_page("Retail", field="customer_group_name")
    session.post.return_value = fake_response(body={"data": {}})
    docs = [{"customer_group_name": name} for name in ["Retail", "Wholesale", "Guest"]]

    created = create_missing(session, BASE_URL, "Customer Group", docs, "customer_group_name")

    assert created == 2
    posted = [call.kwargs["json"] for call in session.post.call_args_list]
    assert posted == [{"customer_group_name": "Wholesale"}, {"customer_group_name": "Guest"}]


def test_create_missing_creates_nothing_when_all_exist():
    session = Mock()
    session.get.return_value = names_page("Retail", "Wholesale", field="customer_group_name")
    docs = [{"customer_group_name": "Retail"}, {"customer_group_name": "Wholesale"}]

    created = create_missing(session, BASE_URL, "Customer Group", docs, "customer_group_name")

    assert created == 0
    session.post.assert_not_called()


def test_create_missing_ignores_case_like_erpnext():
    session = Mock()
    session.get.return_value = names_page("15056BL", field="item_code")
    docs = [{"item_code": "15056bl"}]

    created = create_missing(session, BASE_URL, "Item", docs, "item_code")

    assert created == 0
    session.post.assert_not_called()


def test_list_values_sends_fields_and_filters():
    session = Mock()
    session.get.return_value = names_page("536365", field="custom_source_invoice")
    filters = [["docstatus", "=", 1]]

    rows = list_values(session, BASE_URL, "Sales Invoice", ["custom_source_invoice"], filters)

    assert rows == [{"custom_source_invoice": "536365"}]
    params = session.get.call_args.kwargs["params"]
    assert json.loads(params["fields"]) == ["custom_source_invoice"]
    assert json.loads(params["filters"]) == filters


def deadlock() -> Mock:
    body = {
        "exc_type": "QueryDeadlockError",
        "exception": "frappe.exceptions.QueryDeadlockError: (1020, 'Record has changed')",
    }
    return fake_response(ok=False, body=body)


def test_insert_retries_database_collisions(monkeypatch):
    waits = []
    monkeypatch.setattr(common.erpnext.time, "sleep", waits.append)
    session = Mock()
    stored_payment = fake_response(body={"data": {"name": "P1"}})
    session.post.side_effect = [deadlock(), deadlock(), stored_payment]

    stored = insert(session, BASE_URL, "Payment Entry", {"reference_no": "536365"})

    assert stored == {"name": "P1"}
    assert waits == [2, 4]


def test_insert_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(common.erpnext.time, "sleep", lambda seconds: None)
    session = Mock()
    session.post.return_value = deadlock()

    with pytest.raises(ERPNextError, match="QueryDeadlockError"):
        insert(session, BASE_URL, "Payment Entry", {"reference_no": "536365"})

    assert session.post.call_count == MAX_ATTEMPTS


def test_insert_does_not_retry_other_errors():
    session = Mock()
    session.post.return_value = fake_response(ok=False, body={"exception": "LinkValidationError"})

    with pytest.raises(ERPNextError):
        insert(session, BASE_URL, "Customer", {"customer_name": "17850"})

    assert session.post.call_count == 1
