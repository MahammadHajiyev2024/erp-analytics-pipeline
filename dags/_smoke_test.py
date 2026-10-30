"""Temporary smoke-test DAG for Phase 9 PR1.

Proves the Airflow stack itself works end to end: the image builds,
Postgres migrates, the scheduler and dag-processor pick up this file, the
API server is reachable, and a task actually runs and succeeds. It has no
dependency on ERPNext, Databricks, or any project code.

Removed in PR2 once dags/erp_pipeline.py exists -- see docs/airflow-setup.md.
"""

from __future__ import annotations

import logging
from datetime import datetime

from airflow.sdk import dag, task

logger = logging.getLogger(__name__)


@dag(
    dag_id="_smoke_test",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["phase-9", "smoke-test"],
)
def smoke_test():
    @task
    def hello() -> str:
        logger.info("Airflow stack is up and this task ran successfully.")
        return "ok"

    hello()


smoke_test()
