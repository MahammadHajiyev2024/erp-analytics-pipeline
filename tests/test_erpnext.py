from unittest.mock import Mock

import pytest
import requests

from common.erpnext import (
    PAGE_SIZE,
    TIMEOUT_SECONDS,
    ERPNextError,
    can_read,
    create_missing,
    get_logged_user,
    get_session,
    insert,
    list_names,
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


def names_page(*names: str) -> Mock:
    return fake_response(body={"data": [{"name": name} for name in names]})


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
    session.get.return_value = names_page("Retail")
    session.post.return_value = fake_response(body={"data": {}})
    docs = [{"customer_group_name": name} for name in ["Retail", "Wholesale", "Guest"]]

    created = create_missing(session, BASE_URL, "Customer Group", docs, "customer_group_name")

    assert created == 2
    posted = [call.kwargs["json"] for call in session.post.call_args_list]
    assert posted == [{"customer_group_name": "Wholesale"}, {"customer_group_name": "Guest"}]


def test_create_missing_creates_nothing_when_all_exist():
    session = Mock()
    session.get.return_value = names_page("Retail", "Wholesale")
    docs = [{"customer_group_name": "Retail"}, {"customer_group_name": "Wholesale"}]

    created = create_missing(session, BASE_URL, "Customer Group", docs, "customer_group_name")

    assert created == 0
    session.post.assert_not_called()
