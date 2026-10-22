"""Client for the ERPNext REST API."""

import json
import logging
import os

import requests
from dotenv import load_dotenv

TIMEOUT_SECONDS = 30
PAGE_SIZE = 1000
LOG_EVERY = 500

logger = logging.getLogger(__name__)


class ERPNextError(Exception):
    """ERPNext refused a request; the message includes ERPNext's explanation."""


def get_session(api_key: str, api_secret: str) -> requests.Session:
    """Return a session authenticated with an ERPNext API key and secret."""
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


def error_detail(response: requests.Response) -> str:
    """Return ERPNext's explanation of a failed request, or the start of the response."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    return body.get("exception") or body.get("_server_messages") or response.text[:300]


def list_names(session: requests.Session, base_url: str, doctype: str) -> set[str]:
    """Return the names of all documents of a doctype, fetched page by page."""
    names: set[str] = set()
    start = 0
    while True:
        response = session.get(
            f"{base_url}/api/resource/{doctype}",
            params={
                "fields": json.dumps(["name"]),
                "order_by": "name asc",
                "limit_start": start,
                "limit_page_length": PAGE_SIZE,
            },
            timeout=TIMEOUT_SECONDS,
        )
        if not response.ok:
            raise ERPNextError(f"Listing {doctype} failed: {error_detail(response)}")
        page = response.json()["data"]
        names.update(row["name"] for row in page)
        if len(page) < PAGE_SIZE:
            return names
        start += PAGE_SIZE


def insert(session: requests.Session, base_url: str, doctype: str, doc: dict) -> dict:
    """Create one document and return it as ERPNext stored it."""
    response = session.post(f"{base_url}/api/resource/{doctype}", json=doc, timeout=TIMEOUT_SECONDS)
    if not response.ok:
        raise ERPNextError(f"Creating {doctype} {doc} failed: {error_detail(response)}")
    return response.json()["data"]


def create_missing(
    session: requests.Session, base_url: str, doctype: str, docs: list[dict], name_field: str
) -> int:
    """Create the documents whose name is not in ERPNext yet; return how many were created.

    Running it again creates nothing, and after an interruption it continues where it
    stopped, because existing documents are skipped.
    """
    existing = list_names(session, base_url, doctype)
    missing = [doc for doc in docs if doc[name_field] not in existing]
    logger.info("%s: %d exist, %d to create", doctype, len(docs) - len(missing), len(missing))
    for count, doc in enumerate(missing, start=1):
        insert(session, base_url, doctype, doc)
        if count % LOG_EVERY == 0:
            logger.info("%s: created %d of %d", doctype, count, len(missing))
    return len(missing)


def main() -> None:
    """Check the connection to ERPNext for the pipeline and bootstrap users."""
    load_dotenv()
    base_url = os.environ["ERPNEXT_URL"]

    pipeline = get_session(os.environ["ERPNEXT_API_KEY"], os.environ["ERPNEXT_API_SECRET"])
    print(f"Pipeline user: {get_logged_user(pipeline, base_url)}")
    for doctype in ["Sales Invoice", "Customer", "Journal Entry"]:
        print(f"  Can read {doctype}: {can_read(pipeline, base_url, doctype)}")

    bootstrap = get_session(
        os.environ["ERPNEXT_BOOTSTRAP_API_KEY"], os.environ["ERPNEXT_BOOTSTRAP_API_SECRET"]
    )
    print(f"Bootstrap user: {get_logged_user(bootstrap, base_url)}")


if __name__ == "__main__":
    main()
