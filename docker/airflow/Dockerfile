# Airflow image for the ERP analytics pipeline.
#
# Based on the official Airflow image. The main project's own pyproject.toml
# / uv.lock stay untouched by Airflow entirely -- see docs/airflow-setup.md
# for why. This just adds a minimal extra pip layer with the handful of
# packages the DAG's task callables need to import and call the existing
# extractors/loaders/simulator/bootstrap modules.
#
# No --constraint here: Airflow's constraints file pins exact versions of
# every package it was tested against at release time, including ones that
# aren't actually Airflow dependencies at all (pandas, pyarrow, python-dotenv,
# databricks-sql-connector are only imported by our own code, never by
# apache-airflow-providers-databricks -- see note below). pyproject.toml's
# floors have since moved past that frozen snapshot, so pinning against it
# makes pip's resolver reject an install that's actually fine. Dropping
# --constraint still installs cleanly against Airflow's own real dependency
# ranges (verified: pip upgrades its pre-installed pandas/pyarrow/certifi/
# python-dotenv with no resolution conflict), which is the thing we actually
# need to protect.
#
# Project code itself is bind-mounted by the root docker-compose.yml, not
# copied in here -- editing it during development never requires rebuilding
# this image.

FROM apache/airflow:3.3.1-python3.12

COPY docker/airflow/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
