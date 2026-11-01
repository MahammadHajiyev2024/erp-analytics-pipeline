# Design decisions

Key decisions behind this project, with the reasoning and the main alternative considered.

## 1. ERPNext as the source system

**Decision:** Use a self-hosted ERPNext instance, seeded with real retail data, as the source.
**Why:** Pulling from a real ERP's REST API exercises authentication, pagination, linked
records, and document states, as in real BI work, where ERP data is the most common source.
**Alternative:** Loading the dataset directly into the lakehouse, which would remove the
API extraction entirely.

## 2. ELT instead of ETL

**Decision:** Load raw data first, then transform it inside the lakehouse.
**Why:** Raw data is always preserved, so transformations can be fixed and rebuilt without
re-extracting; the lakehouse does the heavy processing.
**Alternative:** Transforming in Python before loading (ETL), which loses the raw record.

## 3. Medallion architecture on Databricks

**Decision:** Organize the lakehouse into bronze (raw), silver (cleaned), and gold
(business-ready) layers on Databricks Free Edition.
**Why:** Clear responsibilities per layer, a widely used industry pattern, and a cloud
platform at no cost.
**Alternative:** A self-built PostgreSQL warehouse, which is simpler but not cloud-based
and not a lakehouse.

## 4. Custom Python extraction

**Decision:** Write the extractors and loaders in Python.
**Why:** Full control over pagination, incremental loading, retries, and error handling,
and these are the skills the project aims to demonstrate.
**Alternative:** A managed connector tool such as Airbyte, which hides that logic.

## 5. dbt for transformations

**Decision:** Build silver and gold models with dbt.
**Why:** SQL transformations that are version-controlled, tested, and documented, with
automatic lineage.
**Alternative:** PySpark notebooks, which are harder to test and review.

## 6. Airflow for orchestration, in Docker

**Decision:** Run the daily pipeline with Apache Airflow, in Docker containers.
**Why:** Scheduling, dependencies, retries, and alerting, in the most widely used
open-source orchestrator, reproducible with Docker Compose.
**Alternative:** Scheduled scripts, which offer no retries, dependencies, or monitoring.

## 7. Least-privilege API access

**Decision:** The pipeline authenticates as a dedicated, read-only ERPNext integration user.
**Why:** A leaked key cannot change or delete data.
**Alternative:** Using an administrator account, which is simpler but risky.

## 8. Incremental extraction

**Decision:** Extract only records changed since the last run, using ERPNext's `modified`
timestamp as a watermark.
**Why:** Daily runs stay fast as data grows.
**Alternative:** Full reloads every run, which become slower every day.

## 9. Revenue excludes tax

**Decision:** Revenue is based on net amounts (`net_amount`, `net_total`), never on totals
including VAT.
**Why:** Tax is collected for the government and is not the company's income.
**Alternative:** Using invoice grand totals, which would overstate revenue.

## 10. Books in GBP, reporting in USD

**Decision:** The company records transactions in GBP; the gold layer converts to USD using
daily FRED exchange rates.
**Why:** Matches the source data exactly, and mirrors how multinational companies report
to a parent company.
**Alternative:** Converting prices to USD when loading, which distorts the original data.

## 11. Staged historical load

**Decision:** The bootstrap loaded one month first, verified it, then loaded and verified the
full 26-month history (28 November 2023 to 5 December 2025) one month at a time, stopping at
the first month that failed.
**Why:** A fast first build on a 16 GB laptop proves the pipeline end to end before committing
to the full load; loading month by month with a backup after each isolates a failure to one
month instead of redoing everything.
**Alternative:** Loading everything up front, which delays the first working pipeline and
makes a failure harder to isolate.

## 12. Power BI semantic model as the analytical layer

**Decision:** Use a Power BI semantic model (a tabular model) on the gold star schema.
**Why:** It provides fast slicing, drilling, and reusable measures, the modern successor
to OLAP cubes.
**Alternative:** A separate multidimensional OLAP cube, a largely legacy technology.

## 13. Calendar fiscal year

**Decision:** The company's fiscal year runs from January to December.
**Why:** It matches the US parent company's reporting year and keeps year-over-year
analysis simple, with no separate fiscal calendar in `dim_date`.
**Alternative:** An April-to-March fiscal year, common in the UK, which would need fiscal
period logic in every report.

## 14. Shift dates by 730 weeks

**Decision:** All source dates move forward by exactly 730 weeks (5,110 days), so the
history runs from 28 November 2023 to 5 December 2025.
**Why:** A whole number of weeks keeps every order on its original weekday, and 730 weeks
is three days short of 14 years, so the November peak stays in November. The history
covers two complete calendar years (2024 and 2025) for year-over-year analysis.
**Alternative:** Shifting by exactly 14 years, which keeps calendar dates but moves every
order three weekdays later, creating a weekly pattern the business never had.

## 15. Simulate new activity by replaying history

**Decision:** The simulator generates each new day by replaying the same weekday 52 weeks
earlier, with deterministic variation, growth, new customers, successor products, and
occasional changes and cancellations (see the simulator rules).
**Why:** Replaying real days keeps what is hard to invent, such as which products are
bought together, each customer's usual basket, seasonality, and closed days, while
hash-based variation keeps every run reproducible and idempotent.
**Alternative:** Generating invoices from fitted statistical distributions, which is more
flexible but loses the correlations between customers, products, and seasons.

## 16. Ingestion to bronze via landing volume and COPY INTO
**Decision:** Extractors write raw records as JSON Lines (.jsonl) files into a Databricks Unity Catalog Volume (`erp_analytics.bronze.landing`), which are then ingested into bronze Delta tables using Databricks `COPY INTO`.
**Why:**
- **Built-in Idempotency:** `COPY INTO` tracks loaded files natively, preventing duplicate ingestion if a pipeline batch is re-run.
- **Compute Efficiency:** Bulk loading one file via `COPY INTO` on a 2X-Small warehouse consumes far fewer compute credits and runtime than running thousands of individual `INSERT` statements.
- **Auditability and Replayability:** Raw responses remain archived in the landing volume, allowing the bronze layer to be rebuilt without re-querying ERPNext.
- **Decoupled Architecture:** Network uploads from Python and warehouse compute run independently; warehouse pauses do not interrupt extraction.
- **JSON Lines Representation:** Preserves the exact nested payloads returned by the ERPNext REST API until dbt flattens and types them in the silver layer.
**Alternative:** Direct row-by-row `INSERT` statements over SQL, which is slow for large datasets (over 1M rows), consumes daily quotas, and provides no raw file archive.
**Implementation Note (SDK vs SQL Connector):**Volume uploads use the Databricks SDK (`WorkspaceClient.files.upload`) rather than SQL `PUT` commands. The SDK uploads directly via the Databricks control plane without requiring the SQL warehouse to be running, preserving the Free Edition daily compute quota. The warehouse is started only when executing `COPY INTO` via `databricks-sql-connector`.

**Update (Phase 8):** Bronze tables store each record whole, as a `VARIANT` column `raw`,
read with `FILEFORMAT = TEXT` and `parse_json`, plus `name`, `modified`, `docstatus` and the
metadata columns taken out with `get_json_object` for deduplication. Typed columns failed
on ERPNext documents: schema inference typed nested child tables (`items`, `taxes`)
differently from the declared columns, and a daily batch can infer different types again.
Storing the record untyped keeps bronze exactly as received; silver types and flattens it.
Landing files are uploaded with the Databricks SDK (`WorkspaceClient.files.upload`), which
does not need the SQL warehouse running.

## 17. Keyset pagination with a watermark overlap for incremental extraction

**Decision:** List and document extraction both page through ERPNext with keyset pagination
instead of limit/offset: full loads page by `name` (the indexed primary key); incremental loads
page by `(modified, name)`, starting a 2-hour overlap before the watermark. The watermark is the
newest `modified` seen in the list, never a value taken from a fetched document.
**Why:**
- **Offset paging is unsafe on a changing table:** a row updated between two pages shifts every
  row after it, so a page can skip one entirely; ERPNext's hourly stock reposting does this
  continuously. Keyset pagination reads each page from a cursor on the last row seen, so an
  update elsewhere cannot hide a row, and deep pages cost the same as the first.
- **Sorting by `name` is far cheaper than by `modified`:** measured on 1.5 million Stock Ledger
  Entries, a page sorted by `modified` cost about 11 seconds (no index, even filtered) against
  0.1 seconds sorted by `name`. A full load by `name` took about 3 minutes, against an estimated
  6.5 hours by `modified`.
- **The overlap catches late-committing transactions and the UK clock change:** ERPNext stores
  `modified` in local time (Europe/London), which repeats an hour when UK clocks go back in
  October (see [Time zones](architecture.md#time-zones)). A 2-hour overlap is comfortably wider
  than that hour, and also covers ordinary transaction-commit lag. A run where nothing is newer
  than the watermark (only the overlap was re-read) writes or fetches nothing and leaves the
  watermark unchanged.
- **Document extraction's watermark comes from the list, not from the fetched document:**
  fetching one document per GET can take hours for a large doctype, and a document that changes
  after it was listed, but before its turn to be fetched, must still be read again next run. A
  watermark taken from the fetched document's own `modified` could advance past it.
- **A full load cut short by `--max-records` sets no watermark:** the unread remainder must
  still be read as part of a first load next run, not skipped as already incremental.
**Alternative:** Limit/offset pagination, simpler but unsafe on a table that changes during the
run and slower with depth; adding an index on `(modified, name)` in ERPNext, rejected because it
changes the source schema — a decision for whoever administers that instance, not the pipeline.

## 18. Keep `incoming_rate` for cost of sales despite ERPNext's stock reposting

**Decision:** ERPNext's background Repost Item Valuation queue was found silently rewriting old
Stock Ledger Entries. No change was made to ERPNext, and `fact_sales.cost_amount_gbp` still comes
from `qty × incoming_rate` on the Sales Invoice's own stock entries, not from
`stock_value_difference`.
**Why:** Comparing all 69,965 Stock Ledger Entries that reposting rewrote during verification,
`qty_after_transaction`, `stock_value_difference`, `incoming_rate`, and `is_cancelled` never
changed; only `valuation_rate` and `stock_value` changed, on 1,928 entries across 11 ordinary
items (first changes in 2026, none at zero stock, a maximum rate change of £0.22 and a maximum
stock value change of £36.32). The figures cost of sales depends on are unaffected, so tracing
the cause to change a value that never moved was not worth it. A dbt test in silver compares
`qty × incoming_rate` against `stock_value_difference` on each Sales Invoice's stock entries, so
a future divergence is caught rather than assumed away.
**Alternative:** Investigating and silencing the repost queue in ERPNext, which would change the
source system to fix a quantity already confirmed stable; or computing cost of sales from
`stock_value_difference` instead, unnecessary since `incoming_rate` never changed.

## 19. Airflow installed only in its own Docker image, never in `pyproject.toml`/`uv.lock`

**Decision:** `apache-airflow` is never added to `pyproject.toml`/`uv.lock`. `docker/airflow/Dockerfile`
is based on the official `apache/airflow:<version>-python3.12` image, with a minimal extra pip
layer (`databricks-sdk`, `databricks-sql-connector`, `python-dotenv`, `requests`, `pandas`,
`pyarrow`) for the handful of packages the DAG's task callables need to import and call the
existing extractors/loaders/simulator/bootstrap modules. No `apache-airflow-providers-databricks`
either -- `loaders.upload_to_volume`/`loaders.load_*_to_bronze` already open their own Databricks
connections from env vars, so a plain `@task` needs nothing Databricks-aware from Airflow. No
`astronomer-cosmos` yet -- there's nothing to wrap until `dbt/` exists.
**Why:** Resolving `apache-airflow` into the main project's own `uv.lock` risks forcing a version
conflict with the main project's pins to satisfy a dependency of a service, not of pipeline code.
Adding the Databricks provider would work against `CLAUDE.md`'s "DAGs only call them; no business
logic inside DAG files" rule. This also means `uv sync --locked` in CI never changes, and no
contributor running `uv sync` for normal dev work ever installs Airflow.
**Alternative:** Resolving `apache-airflow`/providers into the main `uv.lock`, rejected for the
conflict risk above.
**Implementation note:** The extra pip layer was first installed with `--constraint` against
Airflow's own constraints file, meant to stop it fighting Airflow's pinned dependencies. Dropped
during Phase 9 PR1 verification: that file freezes exact versions of every package Airflow was
tested against at release time, including ones Airflow doesn't actually depend on (`pandas`,
`pyarrow`, `python-dotenv`, `databricks-sql-connector` are only imported by this project's own
code, never by an installed provider) -- `pyproject.toml`'s floors had since moved past that
frozen snapshot, so the constraint rejected an otherwise-fine install. Verified that dropping it
still installs cleanly against Airflow's actual dependency ranges, which is the thing that
actually needed protecting.

## 20. LocalExecutor with a dedicated Postgres metadata database

**Decision:** Run Airflow with `LocalExecutor` and a dedicated `postgres:16` metadata database (its
own Compose service), not `SequentialExecutor`/SQLite, not `CeleryExecutor`/`KubernetesExecutor`.
**Why:** `SequentialExecutor` runs one task at a time, ever -- it would collapse the DAG's
deliberate 6-way parallel extract/load fan-out back into a sequential loop.
`CeleryExecutor`/`KubernetesExecutor` need a message broker and separate long-lived worker
containers, real infrastructure for distributing tasks across machines that one daily DAG with 6
short tasks on one laptop doesn't need. `LocalExecutor` runs tasks as local subprocesses of the
scheduler: genuine parallelism, no broker, no worker containers. Postgres is non-optional with
`LocalExecutor` despite being single-machine: `LocalExecutor` updates multiple tasks' state at the
same moment, and Airflow only supports SQLite with `SequentialExecutor`, where there's never more
than one writer. The triggerer and Redis/Celery workers/Flower are skipped entirely -- nothing in
this DAG defers, and nothing uses `CeleryExecutor`.
**Alternative:** `SequentialExecutor` + SQLite, simplest but serializes the fan-out;
`CeleryExecutor`/`KubernetesExecutor`, unneeded infrastructure at this scale.
**Implementation note:** Adds roughly 1-1.5 GB idle RAM on top of ERPNext's own ~2-3 GB -- see the
laptop resource agreement in `CLAUDE.md`.

## 21. Airflow and ERPNext as two independent Docker stacks

**Decision:** Airflow's root `docker-compose.yml` is a separate stack from
`docker/erpnext/compose.yaml` -- different file, different `name:`, not joined to ERPNext's
internal `frappe_network`. Airflow's containers reach ERPNext over its published host port
(`http://host.docker.internal:${ERPNEXT_PORT:-8080}` from inside a container), exactly like every
extractor, pytest, and a browser already do from outside Docker.
**Why:** Joining Airflow to ERPNext's internal network would make DAG connectivity depend on
ERPNext's internal service names -- an unrelated coupling to a system this stack doesn't own. The
one consequence: inside a Linux container on Docker Desktop for Windows, `localhost` means the
container itself, not the host machine, which is why `ERPNEXT_URL` needs the
`host.docker.internal` override (documented in `docs/airflow-setup.md` as a first-time Docker
gotcha).
**Alternative:** One shared Compose file/network for both stacks, rejected for the coupling above;
the two stacks are brought up/down independently.

## 22. dbt installed in its own independent `uv` project (`dbt/`), not the root `pyproject.toml`/`uv.lock`

**Decision:** `dbt/pyproject.toml` and `dbt/uv.lock` are a second, separate `uv` project -- own
`.venv`, own dependency resolution -- invoked via `uv run --directory dbt ...`.
**Why:** Tried putting `dbt-core`/`dbt-databricks` in the root project's `dev` dependency group
first (the original reasoning: dbt is invoked directly and often, like `pytest`/`ruff`, and
doesn't ship the kind of global constraints file that forced Airflow's isolation in ADR 19);
`uv lock` failed for real -- `dbt-databricks` (every release up to and including 1.13.0,
confirmed via PyPI) pins `databricks-sdk<0.118.0` and `databricks-sql-connector<4.4.1`,
incompatible with this project's existing `databricks-sdk>=0.157.0`/
`databricks-sql-connector>=4.8.0`. A different mechanism than ADR 19's constraints-file conflict
(ordinary incompatible pins, not a floating constraints file), same practical effect. Isolating
dbt into its own `uv` project avoided it without downgrading the loaders' Databricks library
versions. `sqlfluff`/`sqlfluff-templater-dbt` are duplicated into `dbt/pyproject.toml` too,
since sqlfluff's dbt templater must import dbt-core itself and so has to run from the same
environment. When Cosmos is added in a later PR, `dbt-core`/`dbt-databricks` additionally get
duplicated into `docker/airflow/Dockerfile`'s existing pip layer, the same way `pandas`/
`pyarrow`/`databricks-sql-connector` already are.
**Alternative:** Downgrade the root project's `databricks-sdk`/`databricks-sql-connector` pins
to whatever `dbt-databricks` tolerates, rejected -- loses newer SDK/connector behavior the
loaders use, and every future bump of those libraries would risk re-breaking `dbt-databricks`
compatibility again.

## 23. CI runs dbt for real, against an isolated `ci` schema, with a second, narrowly-scoped token

**Decision:** Unlike the fully-mocked Python test suite, CI executes real `dbt build` against
the real, shared `bronze` schema, writing into a dedicated `ci` schema, authenticated with a
second Databricks PAT scoped (via Unity Catalog `GRANT`s) to read `bronze` and fully use `ci`
only -- no access to `silver`/`gold`.
**Why:** dbt tests only mean something against real materialized tables; there's no meaningful
way to mock a SQL warehouse. Databricks Free Edition's SQL warehouse is zero-cost serverless
compute, so there's no cost objection. A second, narrower token means a leaked CI secret can't
touch production data. GitHub Actions doesn't expose secrets to workflows triggered by pull
requests from forks, covering the main leak vector even on a public repo.
**Alternative:** Reuse the existing pipeline PAT for CI, rejected -- would give CI the same
bronze-write privilege as production loaders, a far larger blast radius if it ever leaked.
**Status: not yet achieved, open as of this writing.** A Databricks PAT always carries its
owning user's full privileges; Unity Catalog `GRANT`s attach to principals (users, groups,
service principals), never to individual tokens. A second PAT under the *same* integration
user has identical rights to the first, so the `GRANT ... TO <ci-token-user>` steps in
`docs/dbt-setup.md` do not currently narrow anything. Free Edition has no service principals
(`docs/databricks-setup.md`), so the real fix needs a second, distinct workspace user -- not
yet decided whether Free Edition supports that. Until resolved, CI's
token has the same privileges as the loaders' token, and the "leaked CI secret can't touch
production data" property above does not hold. Revisit before relying on it.
