"""Client for the ERPNext REST API."""

import os

import requests
from dotenv import load_dotenv

TIMEOUT_SECONDS = 30


def get_session() -> requests.Session:
    """Return a session authenticated with the pipeline's API key and secret."""
    api_key = os.environ["ERPNEXT_API_KEY"]
    api_secret = os.environ["ERPNEXT_API_SECRET"]
    session = requests.Session()
    session.headers["Authorization"] = f"token {api_key}:{api_secret}"
    return session


def get_logged_user(session: requests.Session, base_url: str) -> str:
    """Return the ERPNext user that the session is authenticated as."""
    response = session.get(
        f"{base_url}/api/method/frappe.auth.get_logged_user",
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["message"]


def can_read(session: requests.Session, base_url: str, doctype: str) -> bool:
    """Return True if the session may list documents of the given doctype."""
    response = session.get(
        f"{base_url}/api/resource/{doctype}",
        params={"limit_page_length": 1},
        timeout=TIMEOUT_SECONDS,
    )
    return response.ok


def main() -> None:
    """Check the connection to ERPNext and the pipeline user's permissions."""
    load_dotenv()
    base_url = os.environ["ERPNEXT_URL"]
    session = get_session()

    print(f"Connected to {base_url} as {get_logged_user(session, base_url)}")
    for doctype in ["Sales Invoice", "Customer", "Journal Entry"]:
        print(f"Can read {doctype}: {can_read(session, base_url, doctype)}")


if __name__ == "__main__":
    main()
