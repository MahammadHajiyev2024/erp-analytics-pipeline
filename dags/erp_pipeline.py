"""The Phase 9 daily pipeline: simulate -> extract -> load bronze -> dbt (stub) -> notify.

Business logic lives in extractors/loaders/simulator -- this file only wires them together, per
CLAUDE.md's "DAGs only call them; no business logic inside DAG files" rule. See
docs/airflow-setup.md for the task graph and how to verify this DAG.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

from dags.paths import SOURCES, VOLUME, extract_kwargs
from loaders import upload_to_volume

logger = logging.getLogger(__name__)


@dag(
    dag_id="erp_pipeline",
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["phase-9"],
)
def erp_pipeline() -> None:
    @task
    def simulate_erpnext_activity() -> None:
        # Not --test: this DAG runs against the real ERPNext, never the dev/test instance.
        result = subprocess.run([sys.executable, "-m", "simulator.run"], check=False)
        if result.returncode != 0:
            raise RuntimeError(f"simulator.run exited with status {result.returncode}")

    @task
    def extract_source(folder: str) -> str | None:
        extract_fn = next(fn for name, fn, _ in SOURCES if name == folder)
        path = extract_fn(**extract_kwargs(folder))
        # XCom serializes return values as JSON; Path isn't JSON-serializable.
        return str(path) if path else None

    @task
    def load_source(folder: str, path_str: str | None) -> int:
        if path_str is None:
            return 0
        load_fn = next(fn for name, _, fn in SOURCES if name == folder)
        volume_path = upload_to_volume(Path(path_str), f"{VOLUME}/{folder}")
        return load_fn(volume_path)

    @task
    def dbt_build_stub() -> None:
        logger.info("dbt build stub -- not yet implemented; replace once dbt/ exists.")

    @task(trigger_rule="all_done")
    def notify_pipeline_status() -> None:
        logger.info("Pipeline run finished -- check the Grid view for per-task status.")

    simulate = simulate_erpnext_activity()
    dbt_task = dbt_build_stub()
    notify_task = notify_pipeline_status()

    for folder, _, _ in SOURCES:
        extracted = extract_source.override(task_id=f"extract_{folder}")(folder)
        loaded = load_source.override(task_id=f"load_{folder}")(folder, extracted)
        simulate >> extracted
        loaded >> dbt_task

    dbt_task >> notify_task


erp_pipeline()
