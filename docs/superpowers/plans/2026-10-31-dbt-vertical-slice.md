# dbt Vertical Slice (Phase 10, Part 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the dbt project against the project's Databricks warehouse and prove the
full path — local dev, one real silver model (`stg_customer`), dbt tests, and CI running those
tests for real against an isolated `ci` schema — before building the remaining silver models
and any gold model in follow-up PRs.

**Architecture:** A new `dbt/` project (dbt-databricks adapter) sits alongside the existing
Python extractors/loaders, reading bronze's `erpnext_customer` table and writing a deduplicated,
typed `stg_customer` table into the `silver` schema. CI runs the same build against a `ci`
schema, using a second, narrower-scoped Databricks token so a leaked CI secret can't touch
production data.

**Tech Stack:** dbt-core, dbt-databricks, sqlfluff (Databricks dialect, dbt templater), uv,
GitHub Actions, Databricks Unity Catalog (SQL warehouse, PAT auth).

**Spec:** `docs/superpowers/specs/2026-10-31-dbt-vertical-slice-design.md`

## Global Constraints

- Secrets only from environment variables; never commit `.env` or any real credential
  (`CLAUDE.md`).
- CI's Databricks credentials live only in encrypted GitHub Actions repo secrets.
- Dependencies managed with `uv`, pinned in `pyproject.toml`/`uv.lock` (`CLAUDE.md`).
- SQL linted with `sqlfluff`, Databricks dialect (`CLAUDE.md`).
- dbt models in snake_case, prefixed `stg_` (silver) / `dim_`, `fact_` (gold) (`CLAUDE.md`).
- Repo layout already names `dbt/` with `models/silver`, `models/gold`, `snapshots`, `tests`
  (`CLAUDE.md`) — this plan only populates `models/silver`.
- Bronze's `erpnext_customer` table shape (fixed, already loaded):
  `name STRING, modified STRING, docstatus INT, raw VARIANT, _ingested_at TIMESTAMP,
  _source STRING, _batch_id STRING` (`loaders/bronze.py`).
- Dedup tiebreak (already decided, `docs/extraction-and-bronze.md`): for rows sharing the same
  `name`, keep the greatest `modified`; if `modified` ties, keep the greatest `_ingested_at`.
- `docstatus` 2 = cancelled; silver removes drafts and cancellations (`CLAUDE.md`,
  `docs/architecture.md`). `docstatus IS NULL` (legacy incomplete rows, see below) is **not**
  cancelled and must be kept.
- CI reads the real, shared `bronze` schema; only the `ci` write target is isolated (spec,
  confirmed against `CLAUDE.md`'s "one catalog with schemas bronze, silver, gold (plus `ci`)").
- CI uses a second Databricks PAT (not the loaders' existing one), scoped by Unity Catalog
  `GRANT`s to `SELECT` on `bronze` and full rights on `ci` only — nothing on `silver`/`gold`
  (spec, user-confirmed).
- `stg_customer` is current-state-only (no SCD Type 2 in silver; that's a later, gold-layer PR).
- Astronomer Cosmos, `docker/airflow/Dockerfile`, and `dags/erp_pipeline.py` are out of scope.
  `dbt_build_stub` keeps logging its placeholder message.
- **Running `dbt build`/`dbt test`/`dbt debug` against the real Databricks warehouse (any
  target, including `dev`) is "touching a real system."** Per the project's working
  agreements, this is something the user runs, or something an agent session only runs after
  asking first each time — the same rule that already applies to Databricks SQL and to running
  extractors/loaders/the simulator/bootstrap against real systems. Every verification step
  below that invokes `dbt` needs that confirmation at execution time; it is not a standing
  exception the way `pytest`/`ruff` are.

## Review Focus

- A Customer row with `docstatus IS NULL` (the legacy, incomplete rows from an earlier buggy
  extractor run, documented in `docs/extraction-and-bronze.md`) must still appear in
  `stg_customer` — a filter that only tests `docstatus = 1` (submitted) would silently drop
  real master data. Covered by Task 2's singular test comparing counts.
- A Customer row with `docstatus = 2` (cancelled) must **not** appear in `stg_customer`.
  Covered by Task 2's singular test asserting zero cancelled rows in the output.
- Running `dbt build` twice in a row (the incremental merge re-running with nothing new to
  load) must not duplicate or error — merge-on-`customer_id` has to actually dedupe against
  what's already in the target table, not just within one batch. Covered by Task 2's
  idempotency check.
- The CI-scoped Databricks token must actually be denied when it tries to write outside `ci`
  (a `GRANT` that's broader than intended defeats the whole reason for a second token).
  Covered by Task 3's manual permission-denial check.
- The `dev` and `ci` dbt targets must resolve to the schemas they're supposed to (`silver` and
  `ci` respectively) — a copy-paste mistake in `profiles.yml` would make CI silently build into
  the real `silver` schema. Covered by Task 1's `dbt debug` check (which prints the resolved
  schema) and Task 3's end-to-end CI run.

---

### Task 1: dbt project scaffold and dependencies

**Files:**
- Create: `dbt/pyproject.toml` (dbt's own, independent `uv` project)
- Create: `dbt/dbt_project.yml`
- Create: `dbt/profiles.yml`
- Create: `dbt/.sqlfluff`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a dbt project named `erp_analytics`, profile `erp_analytics`, with two targets —
  `dev` (schema `silver`) and `ci` (schema `ci`) — that every later task's `dbt` invocations use
  via `uv run --directory dbt dbt <command> --profiles-dir . --target <dev|ci>`.

**Note (ruling made during implementation):** the original plan put `dbt-core`/`dbt-databricks`
in the root `pyproject.toml`'s `dev` group. `uv lock` failed for real — dbt-databricks pins
`databricks-sdk<0.118.0`/`databricks-sql-connector<4.4.1`, incompatible with this project's
existing `databricks-sdk>=0.157.0`/`databricks-sql-connector>=4.8.0`. dbt now lives in its own
independent `uv` project under `dbt/`, with its own lockfile and `.venv`, so neither project's
resolution constrains the other. See `docs/superpowers/specs/2026-10-31-dbt-vertical-slice-design.md`'s
decision 2 and this plan's ledger for the full finding.

- [ ] **Step 1: Write `dbt/pyproject.toml`**

`sqlfluff`'s dbt templater (Task 2 needs it to lint `stg_customer.sql`) must import `dbt-core`
itself to compile Jinja, so it has to run from this same environment, not the root project's —
`sqlfluff` and `sqlfluff-templater-dbt` are duplicated here for that reason, alongside the
copy already in the root `pyproject.toml`'s `dev` group (used for any future non-dbt SQL):

```toml
[project]
name = "erp-analytics-dbt"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "dbt-core>=1.8.0",
    "dbt-databricks>=1.8.0",
    "sqlfluff>=4.4.0",
    "sqlfluff-templater-dbt>=4.4.0",
]
```

- [ ] **Step 2: Lock and sync dbt's own project**

Run: `uv lock --directory dbt && uv sync --directory dbt`
Expected: resolves cleanly (no version conflict — nothing here constrains or is constrained by
the root project), `uv run --directory dbt dbt --version` reports dbt-core and the databricks
adapter.

- [ ] **Step 3: Write `dbt/dbt_project.yml`**

```yaml
name: 'erp_analytics'
version: '1.0.0'
config-version: 2
profile: 'erp_analytics'

model-paths: ["models"]
test-paths: ["tests"]
snapshot-paths: ["snapshots"]
clean-targets: ["target", "dbt_packages"]

models:
  erp_analytics:
    silver:
      +materialized: incremental
```

- [ ] **Step 4: Write `dbt/profiles.yml`**

`DATABRICKS_HOST` is stored with its `https://` scheme (used as-is by the Python loaders, which
strip it themselves in `common/databricks.py`); dbt-databricks needs the bare hostname, so strip
it in Jinja instead of adding a second env var:

```yaml
erp_analytics:
  target: dev
  outputs:
    dev:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') | replace('https://', '') | replace('http://', '') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      catalog: "{{ env_var('DATABRICKS_CATALOG', 'erp_analytics') }}"
      schema: silver
      threads: 4
    ci:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') | replace('https://', '') | replace('http://', '') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_CI_TOKEN') }}"
      catalog: "{{ env_var('DATABRICKS_CATALOG', 'erp_analytics') }}"
      schema: ci
      threads: 4
```

- [ ] **Step 5: Write `dbt/.sqlfluff`**

Lives inside `dbt/`, not the repo root — `sqlfluff` runs with `dbt/` as the working directory
(via `uv run --directory dbt sqlfluff ...`), so `project_dir`/`profiles_dir` are `.`, not `dbt`:

```ini
[sqlfluff]
dialect = databricks
templater = dbt
sql_file_exts = .sql

[sqlfluff:templater:dbt]
project_dir = .
profiles_dir = .
profile = erp_analytics
target = dev
```

- [ ] **Step 6: Verify the connection (ask the user to confirm before running — this hits the
  real Databricks warehouse)**

Run: `uv run --directory dbt dbt debug --profiles-dir . --target dev`
Expected: `All checks passed!`, with `schema: silver` shown in the printed connection info.

- [ ] **Step 7: Commit**

```bash
git add dbt/pyproject.toml dbt/uv.lock dbt/dbt_project.yml dbt/profiles.yml dbt/.sqlfluff
git commit -m "chore: scaffold dbt project with dev/ci Databricks targets"
```

---

### Task 2: `stg_customer` silver model

**Files:**
- Create: `dbt/models/silver/_silver__sources.yml`
- Create: `dbt/models/silver/stg_customer.sql`
- Create: `dbt/models/silver/_silver__models.yml`
- Create: `dbt/tests/assert_stg_customer_excludes_cancelled.sql`
- Create: `dbt/tests/assert_stg_customer_includes_null_docstatus.sql`

**Interfaces:**
- Consumes: Task 1's project scaffold (`dev`/`ci` targets).
- Produces: `{{ ref('stg_customer') }}`, columns `customer_id` (string, unique, not null),
  `customer_name` (string), `territory` (string), `customer_group` (string), `modified`
  (string), `docstatus` (int, nullable), `_ingested_at` (timestamp) — later gold-layer PRs
  (`dim_customer`) consume these exact column names.

- [ ] **Step 1: Declare the bronze source in `dbt/models/silver/_silver__sources.yml`**

```yaml
version: 2

sources:
  - name: bronze
    schema: bronze
    tables:
      - name: erpnext_customer
```

- [ ] **Step 2: Write `dbt/models/silver/stg_customer.sql`**

The dedup tiebreak (greatest `modified`, then greatest `_ingested_at`) and the cancelled/draft
filter are both already-decided rules, not the implementer's choice — pinned here exactly:

```sql
{{ config(materialized='incremental', unique_key='customer_id', incremental_strategy='merge') }}

with ranked as (

    select
        name as customer_id,
        raw:customer_name::string as customer_name,
        raw:territory::string as territory,
        raw:customer_group::string as customer_group,
        modified,
        docstatus,
        _ingested_at,
        row_number() over (
            partition by name
            order by modified desc, _ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_customer') }}
    where docstatus is null or docstatus != 2
    {% if is_incremental() %}
    and _ingested_at > (select max(_ingested_at) from {{ this }})
    {% endif %}

)

select customer_id, customer_name, territory, customer_group, modified, docstatus, _ingested_at
from ranked
where row_num = 1
```

- [ ] **Step 3: Write schema tests in `dbt/models/silver/_silver__models.yml`**

```yaml
version: 2

models:
  - name: stg_customer
    columns:
      - name: customer_id
        tests:
          - unique
          - not_null
      - name: modified
        tests:
          - not_null
```

- [ ] **Step 4: Write the cancelled-exclusion singular test**

`dbt/tests/assert_stg_customer_excludes_cancelled.sql` — a dbt singular test fails if its query
returns any row, so select the violations:

```sql
select customer_id
from {{ ref('stg_customer') }}
where docstatus = 2
```

- [ ] **Step 5: Write the null-docstatus-is-kept singular test**

`dbt/tests/assert_stg_customer_includes_null_docstatus.sql` — compares the deduplicated count of
non-cancelled bronze rows against `stg_customer`'s row count; a mismatch means some row (likely
the `docstatus IS NULL` legacy rows) was wrongly dropped:

```sql
with bronze_deduped as (

    select
        name,
        row_number() over (
            partition by name
            order by modified desc, _ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_customer') }}
    where docstatus is null or docstatus != 2

)

select count(*) as bronze_count
from bronze_deduped
where row_num = 1
having bronze_count != (select count(*) from {{ ref('stg_customer') }})
```

- [ ] **Step 6: Run the build (ask the user to confirm before running — this writes to the real
  `silver` schema)**

Run: `uv run --directory dbt dbt build --profiles-dir . --target dev`
Expected: `stg_customer` builds, all 4 tests (2 schema + 2 singular) pass.

- [ ] **Step 7: Verify idempotency — run it again**

Run: `uv run --directory dbt dbt build --profiles-dir . --target dev` (same command, again)
Expected: same pass/fail result, and `select count(*) from erp_analytics.silver.stg_customer`
(run by the user in the Databricks SQL editor) reports the same row count as before this second
run — the merge did not duplicate rows.

- [ ] **Step 8: Lint the new SQL**

Run: `uv run --directory dbt sqlfluff lint models/silver/stg_customer.sql tests/`
Expected: no violations (fix and re-run if any).

- [ ] **Step 9: Commit**

```bash
git add dbt/models/silver dbt/tests
git commit -m "feat: add stg_customer silver model"
```

---

### Task 3: CI wiring — isolated `ci` schema, scoped token, workflow

**Files:**
- Modify: `.github/workflows/ci.yml` (add dbt steps to the existing `lint-and-test` job)

**Interfaces:**
- Consumes: Task 2's `stg_customer` model and its tests (CI needs something real to build).
- Produces: a green CI run that exercises the `ci` dbt target end to end; nothing downstream in
  this PR depends on CI further, but the next silver-model PR extends these same steps rather
  than re-deciding them.

- [ ] **Step 1: Provision the `ci` schema (the user runs this once, in the Databricks SQL
  editor — same pattern as the existing `bronze`/`silver`/`gold` provisioning in
  `docs/databricks-setup.md`)**

```sql
USE CATALOG erp_analytics;
CREATE SCHEMA IF NOT EXISTS ci;
```

- [ ] **Step 2: Create a second Databricks PAT (the user does this in the Databricks UI, under
  the same integration user already used for the pipeline PAT) and note its principal/user
  name for the grants below.**

- [ ] **Step 3: Grant the new token's user the narrower scope (the user runs this once)**

```sql
GRANT USE CATALOG ON CATALOG erp_analytics TO `<ci-token-user>`;
GRANT USE SCHEMA, SELECT ON SCHEMA erp_analytics.bronze TO `<ci-token-user>`;
GRANT USE SCHEMA, CREATE TABLE, SELECT, MODIFY ON SCHEMA erp_analytics.ci TO `<ci-token-user>`;
```

No grants on `silver`/`gold` for this user — that absence is the point.

- [ ] **Step 4: Verify the scope is actually enforced (the user runs this once, manually,
  before trusting the token in CI)**

Using the new token (e.g. via `databricks-sql-connector` or the SQL editor logged in as that
user), attempt `CREATE TABLE erp_analytics.silver.permission_test (x INT)`.
Expected: permission denied. If it succeeds, the grants in Step 3 are wrong — fix and re-check
before proceeding; a token that can write `silver` defeats this task's entire purpose.

- [ ] **Step 5: Add the GitHub Actions repo secrets (the user does this in GitHub's UI:
  Settings → Secrets and variables → Actions)**

Add `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_CATALOG`, and `DATABRICKS_CI_TOKEN`
(the new, narrowly-scoped PAT from Step 2 — not the loaders' existing token).

- [ ] **Step 6: Add dbt steps to `.github/workflows/ci.yml`'s `lint-and-test` job, after the
  existing "Run tests" step**

dbt lives in its own `uv` project (Task 1's ruling), so CI needs its own sync step first:

```yaml
      - name: Install dbt dependencies
        run: uv sync --directory dbt --locked

      - name: Run dbt build (ci schema)
        env:
          DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
          DATABRICKS_HTTP_PATH: ${{ secrets.DATABRICKS_HTTP_PATH }}
          DATABRICKS_CATALOG: ${{ secrets.DATABRICKS_CATALOG }}
          DATABRICKS_CI_TOKEN: ${{ secrets.DATABRICKS_CI_TOKEN }}
        run: uv run --directory dbt dbt build --profiles-dir . --target ci
```

One build step, not a separate `dbt build` plus `dbt test` — `dbt build` already runs each
model's tests as part of the same DAG, so a second `dbt test` invocation would just repeat work.

- [ ] **Step 7: Open a PR touching only CI-safe content (or push to a branch) to confirm the
  new job step actually runs and passes**

Expected: the Actions run shows "Run dbt build (ci schema)" green, and
`select count(*) from erp_analytics.ci.stg_customer` (run by the user) returns rows.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run dbt build against an isolated ci schema"
```

---

### Task 4: Documentation

**Files:**
- Create: `docs/dbt-setup.md`
- Modify: `docs/design-decisions.md` (append ADR 22 and ADR 23)

**Interfaces:**
- Consumes: the exact commands, file paths, and env var names fixed in Tasks 1–3.
- Produces: nothing later consumes programmatically; this is the human-facing record.

- [ ] **Step 1: Write `docs/dbt-setup.md`**

Cover, mirroring the structure of `docs/airflow-setup.md`: what `dbt/` is for and why it's its
own independent `uv` project (separate `pyproject.toml`/`uv.lock`/`.venv` — not the root one);
the one-time setup step (`uv sync --directory dbt`); the `dev`/`ci` target split and which env
vars each needs (`DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN`/
`DATABRICKS_CI_TOKEN`, `DATABRICKS_CATALOG` — already in `.env.example` for the first three;
`DATABRICKS_CI_TOKEN` is CI-only, set as a GitHub secret, never in local `.env`); the exact
local commands (`uv run --directory dbt dbt debug --profiles-dir . --target dev`, `uv run
--directory dbt dbt build --profiles-dir . --target dev`, `uv run --directory dbt sqlfluff
lint ...`); a note that `dbt build`/`test`/`debug` touch the real warehouse the same way
Databricks SQL queries do, so they're run by the user or confirmed first in an agent session;
cross-reference ADRs 22–23.

- [ ] **Step 2: Append ADR 22 to `docs/design-decisions.md`**

"dbt installed in its own independent `uv` project (`dbt/`), not the root `pyproject.toml`/
`uv.lock`." Decision: `dbt/pyproject.toml` and `dbt/uv.lock` are a second, separate `uv`
project — own `.venv`, own dependency resolution — invoked via `uv run --directory dbt ...`.
Why: tried putting `dbt-core`/`dbt-databricks` in the root project's `dev` group first (the
original reasoning: dbt is invoked directly and often, like `pytest`/`ruff`, and doesn't ship
the kind of global constraints file that forced Airflow's isolation in ADR 19); `uv lock`
failed for real — dbt-databricks (every release up to and including 1.13.0, confirmed via PyPI)
pins `databricks-sdk<0.118.0` and `databricks-sql-connector<4.4.1`, incompatible with this
project's existing `databricks-sdk>=0.157.0`/`databricks-sql-connector>=4.8.0`. A different
mechanism than ADR 19's constraints-file conflict (ordinary incompatible pins, not a floating
constraints file), same practical effect. Isolating dbt into its own `uv` project avoided it
without downgrading the loaders' Databricks library versions. `sqlfluff`/`sqlfluff-templater-dbt`
are duplicated into `dbt/pyproject.toml` too, since sqlfluff's dbt templater must import
dbt-core itself and so has to run from the same environment. When Cosmos is added in a later
PR, `dbt-core`/`dbt-databricks` additionally get duplicated into `docker/airflow/Dockerfile`'s
existing pip layer, the same way `pandas`/`pyarrow`/`databricks-sql-connector` already are.
Alternative: downgrade the root project's `databricks-sdk`/`databricks-sql-connector` pins to
whatever dbt-databricks tolerates, rejected — loses newer SDK/connector behavior the loaders
use, and every future bump of those libraries would risk re-breaking dbt-databricks
compatibility again.

- [ ] **Step 3: Append ADR 23 to `docs/design-decisions.md`**

"CI runs dbt for real, against an isolated `ci` schema, with a second, narrowly-scoped token."
Decision: unlike the fully-mocked Python test suite, CI executes real `dbt build` against the
real, shared `bronze` schema, writing into a dedicated `ci` schema, authenticated with a second
Databricks PAT scoped (via Unity Catalog `GRANT`s) to read `bronze` and fully use `ci` only —
no access to `silver`/`gold`. Why: dbt tests only mean something against real materialized
tables, there's no meaningful way to mock a SQL warehouse; Databricks Free Edition's SQL
warehouse is zero-cost serverless compute so there's no cost objection; a second, narrower token
means a leaked CI secret can't touch production data; GitHub Actions doesn't expose secrets to
workflows triggered by pull requests from forks, covering the main leak vector even on a public
repo. Alternative: reuse the existing pipeline PAT for CI, rejected — would give CI the same
bronze-write privilege as production loaders, a far larger blast radius if it ever leaked.

- [ ] **Step 4: Commit**

```bash
git add docs/dbt-setup.md docs/design-decisions.md
git commit -m "docs: document dbt setup and CI-against-real-Databricks decisions"
```
