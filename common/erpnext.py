"""Client for the ERPNext REST API."""

import json
import logging
import os
import time

import requests
from dotenv import load_dotenv

TIMEOUT_SECONDS = 30
PAGE_SIZE = 1000
LOG_EVERY = 500
MAX_ATTEMPTS = 6
RETRY_BASE_SECONDS = 2
# Database collisions that ERPNext resolves by rolling the request back, so the same
# request can safely be sent again.
TEMPORARY_ERRORS = ("QueryDeadlockError", "QueryTimeoutError")

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
    detail = body.get("exception") or body.get("_server_messages") or body.get("exc_type")
    return detail or response.text[:300]


def list_values(
    session: requests.Session,
    base_url: str,
    doctype: str,
    fields: list[str],
    filters: list[list] | None = None,
) -> list[dict]:
    """Return the given fields of all documents of a doctype, fetched page by page.

    filters uses ERPNext's list format, such as [["docstatus", "=", 1]].
    """
    rows: list[dict] = []
    start = 0
    while True:
        params = {
            "fields": json.dumps(fields),
            "order_by": "name asc",
            "limit_start": start,
            "limit_page_length": PAGE_SIZE,
        }
        if filters:
            params["filters"] = json.dumps(filters)
        response = session.get(
            f"{base_url}/api/resource/{doctype}", params=params, timeout=TIMEOUT_SECONDS
        )
        if not response.ok:
            raise ERPNextError(f"Listing {doctype} failed: {error_detail(response)}")
        page = response.json()["data"]
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def list_names(session: requests.Session, base_url: str, doctype: str) -> set[str]:
    """Return the names of all documents of a doctype."""
    return {row["name"] for row in list_values(session, base_url, doctype, ["name"])}


def is_temporary(response: requests.Response) -> bool:
    """Return True if ERPNext rolled the request back because of a database collision."""
    try:
        body = response.json()
    except ValueError:
        return False
    detail = f"{body.get('exc_type', '')} {body.get('exception', '')}"
    return any(error in detail for error in TEMPORARY_ERRORS)


def insert(session: requests.Session, base_url: str, doctype: str, doc: dict) -> dict:
    """Create one document and return it as ERPNext stored it.

    Temporary database collisions are retried, waiting 2, 4, 8, ... seconds between
    attempts; any other refusal raises ERPNextError straight away.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = session.post(
            f"{base_url}/api/resource/{doctype}", json=doc, timeout=TIMEOUT_SECONDS
        )
        if response.ok:
            return response.json()["data"]
        if attempt == MAX_ATTEMPTS or not is_temporary(response):
            break
        wait = RETRY_BASE_SECONDS * 2 ** (attempt - 1)
        logger.warning(
            "%s: database collision, retrying in %d s (attempt %d of %d)",
            doctype,
            wait,
            attempt,
            MAX_ATTEMPTS,
        )
        time.sleep(wait)
    raise ERPNextError(f"Creating {doctype} {doc} failed: {error_detail(response)}")


def create_missing(
    session: requests.Session, base_url: str, doctype: str, docs: list[dict], key_field: str
) -> int:
    """Create the documents whose key is not in ERPNext yet; return how many were created.

    key_field identifies a document, both in docs and in ERPNext, such as item_code or
    custom_source_invoice. Keys are compared ignoring case, as ERPNext does with names.
    Running it again creates nothing, and after an interruption it continues where it
    stopped, because existing documents are skipped.
    """
    rows = list_values(session, base_url, doctype, [key_field])
    existing = {str(row[key_field]).casefold() for row in rows if row.get(key_field)}
    missing = [doc for doc in docs if str(doc[key_field]).casefold() not in existing]
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
