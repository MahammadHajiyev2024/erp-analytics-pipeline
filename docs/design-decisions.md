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

## 23. CI runs dbt for real, against an isolated `ci` schema, authenticated as a second, narrowly-granted workspace user

**Decision:** Unlike the fully-mocked Python test suite, CI executes real `dbt build` against
the real, shared `bronze` schema, writing into a dedicated `ci` schema. CI authenticates as a
genuinely separate Databricks user (`mhajiyev17@gmail.com`, invited specifically for this),
granted only `SELECT`/`USE SCHEMA` on `bronze` and full use of `ci` -- no grants on
`silver`/`gold` at all. A leaked CI secret can read `bronze` and fully use `ci`, but cannot
touch `silver`/`gold`.
**Why real dbt build, not mocked:** dbt tests only mean something against real materialized
tables; there's no meaningful way to mock a SQL warehouse. Databricks Free Edition's SQL
warehouse is zero-cost serverless compute, so there's no cost objection.
**Why a second user, not a second token under the same user:** a Databricks PAT always carries
its owning *user's* full privileges -- Unity Catalog `GRANT`s attach to principals (users,
groups, service principals), never to individual tokens. A second PAT under the same
integration user would have identical rights to the first, narrowing nothing. Confirmed Free
Edition allows inviting a second real workspace user, and granted that user correctly --
`SHOW GRANTS ON SCHEMA erp_analytics.ci` confirmed `CREATE TABLE`/`MODIFY`/`SELECT`/`USE
SCHEMA`; no grants exist on `silver`/`gold` for that user.
**The detour, and the actual fix:** getting a *usable token* for that second user took two
false starts before landing on the real cause.
1. Databricks' "scoped PAT" feature (GA April 2026) was tried first, picking various scopes
   (`all-apis`, explicit `sql`). Every attempt failed identically at the SQL connector's Thrift
   `OpenSession` call: `databricks.sql.exc.RequestError: ... Credential was not sent or was of
   an unsupported type for this API`. A probe script
   (`data/scratch/probe_scoped_pat.py`) confirmed the token itself was valid -- it
   authenticated fine as that second user when the connector's newer "kernel" transport was
   used instead of Thrift (`use_kernel=True`) -- so the problem was specific to Thrift, not the
   token or the user.
2. The real cause: Databricks tokens have an `autoscope_enabled` setting that defaults to on
   for long-lived tokens, which silently converts an ostensibly "full access" token into the
   new scoped format after creation -- regardless of which scope was picked in the UI. This,
   not the scope choice itself, is what produced a Thrift-unreadable token every time.
   **The fix:** create the token via `POST /api/2.0/token/create` with `"scopes": []` *and*
   `"autoscope_enabled": false` explicitly. That keeps the token in the original, Thrift-
   readable format. Re-ran the same probe (this time without `use_kernel`, i.e. the real
   Thrift path dbt-databricks actually uses) and it connected successfully as the second user.
   `dbt-databricks` only ever uses the Thrift backend -- it doesn't expose `use_kernel`
   anywhere in `profiles.yml` -- but that no longer matters, since the fixed token doesn't need
   it.
**Alternative considered and rejected:** a service principal with OAuth M2M -- the standard
mechanism for giving automation its own identity. Not pursued to a test, because Databricks'
own docs say Free Edition has no account console or account-level API access, which
service-principal OAuth depends on (a Databricks-employee community reply attributes an
unrelated service-principal failure on Free Edition to exactly this). Moot once the second-user
PAT route worked.
**Status: achieved.** CI authenticates as a distinct, narrowly-granted principal; a leaked CI
secret cannot reach `silver`/`gold`.

## 24. Gold surrogate keys are deterministic hashes, not identity columns

**Decision:** Every gold dimension's surrogate key (`customer_key`, `product_key`, etc.) is a
deterministic hash of its natural key (and, for SCD2 rows, `valid_from`), produced with
Databricks' native `hash()`/`xxhash64()` and cast to `bigint` -- not a database `IDENTITY`
column.
**Why:** The pipeline rebuilds gold incrementally, not from a single full load. A hash is
stateless and reproducible -- the same natural key always yields the same integer, with no
run-to-run coordination needed, matching the deterministic `row_number()`/`merge` style every
silver model already uses. An `IDENTITY` column requires guaranteeing a given natural key never
gets reassigned a different number across incremental runs, which is state that has to be
protected carefully and has no equivalent pattern elsewhere in this codebase.
**Alternative:** A database `IDENTITY`/auto-increment column, rejected for the coordination risk
above, and for introducing a new, order-dependent key style alongside the existing stateless one.

## 25. `dim_customer` SCD Type 2 history is reconstructed from bronze, not built with `dbt snapshot`

**Decision:** `dim_customer`'s version history (`valid_from`, `valid_to`, `is_current`) is built
by a custom model reading `bronze.erpnext_customer` directly, using `lag()` over each customer's
rows ordered by `modified` to detect real attribute changes and turn them into version
boundaries -- not dbt's built-in `snapshot` materialization.
**Why:** `dbt snapshot` only starts recording history from the first time it's run; it has no way
to retroactively discover changes that happened before that. This project's two years of
simulated history already contain real `customer_group` changes from the simulator's monthly
segment reviews, fully captured in bronze because bronze is append-only and extraction is
incremental on `modified`. A plain snapshot run today would attribute every historical sale to
whatever segment the customer happens to be in *now*, silently defeating the documented reason
this dimension is SCD2 at all (`docs/data-model.md`: "keeps the customer's territory and segment
at the time of sale").
**Why full-refresh, not incremental:** incrementally merging newly-detected versions into an
already-partial reconstructed history is one of the hardest parts of hand-rolling SCD2 -- it's
why most teams use `dbt snapshot` specifically to avoid it. Having already given up that
tool for the backfill reason above, the model instead recomputes the entire version history from
bronze on every run (`materialized='table'`). Customer volume is small (bounded by the UCI
dataset), so the recompute cost is negligible.
**Alternative:** Plain `dbt snapshot` starting now, rejected for losing pre-existing segment
history. Incremental merge of version history, rejected as unnecessary complexity at this data
volume, same reasoning as ADR 26 below.

## 26. `dim_date` is generated natively, with the FX carry-forward rate computed once as its own column

**Decision:** `dim_date` is a continuous calendar (every day, no gaps) generated with
Databricks' native `explode(sequence(start_date, end_date, interval 1 day))` -- no new dbt
package. It carries a `usd_per_gbp` column: `stg_exchange_rate` left-joined onto the full date
range, then `last_value(usd_per_gbp) ignore nulls over (order by date rows between unbounded
preceding and current row)` to carry the most recent published rate forward through weekends and
holidays FRED doesn't publish for.
**Why native generation:** no `packages.yml` exists in this repo yet; a native SQL function
avoids adding a dependency (`dbt_utils.date_spine` would otherwise be the standard choice) for a
one-line calendar generator Databricks already provides.
**Why carry-forward lives on `dim_date`, not recomputed per fact:** every fact table already
joins `dim_date` by `date_key` for its posting date. Computing the carried-forward rate once,
as a column on the conformed date dimension, means the window function runs once across the
whole pipeline instead of being duplicated inside `fact_sales` and `fact_purchases` separately.
**Alternative:** `dbt_utils.date_spine`, rejected to avoid a new dependency without asking first
(`CLAUDE.md`). Recomputing the FX carry-forward inside each fact model, rejected as needless
duplication of the same window function.

## 27. Full-refresh `table` materialization for `dim_customer` and `fact_receivables`; incremental `merge` everywhere else in gold

**Decision:** `dim_customer` (SCD2 history) and `fact_receivables` (current-state snapshot) are
both `materialized='table'`, fully recomputed on every run. `dim_product`, `dim_supplier`,
`fact_sales`, `fact_purchases`, and `fact_stock_movements` use the incremental `merge` pattern
already established in silver.
**Why:** both exceptions need a value to change *in place* for an already-existing row --
`dim_customer`'s reconstructed version boundaries, and an invoice's `outstanding_amount`/
`is_overdue` as payments arrive and dates pass with nothing in the source actually changing.
Incrementally merging either correctly is real, error-prone complexity (see ADR 25); a full
recompute sidesteps it entirely. Data volume makes this cheap, not just correct: total invoices
are ~18,887 and customers are in the low thousands (both bounded by the UCI dataset), so
rescanning everything each run costs low-single-digit seconds on Databricks, no different in
practice from a "smart" incremental merge at this size. The whole pipeline runs once daily
(`dags/erp_pipeline.py`, `0 6 * * *`), so "current" means "as of this morning's run" either way.
**Alternative:** Incremental merge for these two models as well, rejected -- the complexity has
no payoff below real scale, and would require solving the hard incremental-SCD2/incremental-
snapshot-fact problem this design otherwise avoids by construction.
