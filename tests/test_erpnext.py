from unittest.mock import Mock

import pytest
import requests

from common.erpnext import TIMEOUT_SECONDS, can_read, get_logged_user, get_session

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
