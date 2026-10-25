"""Databricks connection client and health check."""

import os
import sys
from collections.abc import Generator
from contextlib import contextmanager

from databricks import sql
from databricks.sql.client import Connection
from dotenv import load_dotenv

load_dotenv()


def get_databricks_config() -> dict[str, str]:
    """Validate and return Databricks connection settings from environment."""
    host = os.getenv("DATABRICKS_HOST", "").strip()
    # Strip protocol if present; the connector expects raw hostname
    host = host.removeprefix("https://").removeprefix("http://").rstrip("/")

    http_path = os.getenv("DATABRICKS_HTTP_PATH", "").strip()
    token = os.getenv("DATABRICKS_TOKEN", "").strip()
    catalog = os.getenv("DATABRICKS_CATALOG", "erp_analytics").strip()

    missing = []
    if not host:
        missing.append("DATABRICKS_HOST")
    if not http_path:
        missing.append("DATABRICKS_HTTP_PATH")
    if not token:
        missing.append("DATABRICKS_TOKEN")

    if missing:
        raise ValueError(f"Missing required Databricks settings in .env: {', '.join(missing)}")

    return {
        "server_hostname": host,
        "http_path": http_path,
        "access_token": token,
        "catalog": catalog,
    }


@contextmanager
def get_connection() -> Generator[Connection, None, None]:
    """Yield an open Databricks SQL connection, closing it on exit."""
    config = get_databricks_config()
    conn = sql.connect(
        server_hostname=config["server_hostname"],
        http_path=config["http_path"],
        access_token=config["access_token"],
        catalog=config["catalog"],
    )
    try:
        yield conn
    finally:
        conn.close()


def check_connection() -> None:
    """Run a basic query to verify connection to Databricks SQL Warehouse."""
    print("Testing connection to Databricks...")
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT current_catalog() AS catalog, "
            "current_schema() AS schema, "
            "current_user() AS user"
        )
        row = cursor.fetchone()
        if row:
            print("Connection successful!")
            print(f"  Catalog: {row['catalog']}")
            print(f"  Schema:  {row['schema']}")
            print(f"  User:    {row['user']}")


if __name__ == "__main__":
    try:
        check_connection()
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)
