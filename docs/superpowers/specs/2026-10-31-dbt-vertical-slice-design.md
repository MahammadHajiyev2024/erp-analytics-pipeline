# Design: dbt vertical slice (Phase 10, part 1)

## Intent and why

Phase 10 is dbt silver and gold layers — the real replacement for the `dbt_build_stub` task
in the `erp_pipeline` Airflow DAG. The gold star schema and the silver layer rules are already
fully specified in `docs/data-model.md` and `docs/architecture.md`; what doesn't exist yet is
the dbt project itself, or any proof that dbt actually runs cleanly against this project's
Databricks warehouse, in local dev and in CI.

Rather than building the whole dbt project (6 silver models, 4 facts, 4 dims, snapshots, CI,
and Cosmos orchestration) in one PR, this is the first of several: a vertical slice that stands
up the dbt project and proves the full path — local dev, a real silver model, dbt tests, and CI
running those tests against a real (but isolated) Databricks schema — on the single simplest
entity, Customer. Every later PR (remaining silver models, gold dimensions, gold facts,
Cosmos/Airflow wiring) builds on this one without re-deciding the mechanics.

This mirrors how every earlier phase in this project was sliced (Airflow: scaffolding PR then
DAG PR; bronze: one loader-per-source PR; bootstrap: master-data then invoices then payments),
per `CLAUDE.md`'s "keep changes small enough to review as a single pull request" rule.

## Goals

- A working dbt project at `dbt/`, connecting to the existing Databricks warehouse.
- One real silver model, `stg_customer`, built from bronze's `Customer` table.
- dbt tests on that model (schema tests at minimum).
- CI runs `dbt build` and `dbt test` for real, against a new, isolated `ci` schema — not mocked.
- SQL linted with `sqlfluff` (Databricks dialect), per existing project convention.
- Documented: a new `docs/dbt-setup.md` (or similar) covering local dbt commands, plus any
  ADRs for decisions made in this design (dependency placement, CI hitting real Databricks).

## Non-goals (this PR)

- The other five silver models (Item, Sales Invoice, Purchase Invoice, Stock Ledger Entry, FRED
  exchange rates). Follow-up PR(s).
- Any gold model (facts, dimensions, snapshots for `dim_customer`'s SCD Type 2). Follow-up PR(s).
- Astronomer Cosmos, the Airflow provider, or any change to `docker/airflow/Dockerfile` or
  `dags/erp_pipeline.py`. `dbt_build_stub` keeps logging its placeholder message until a later
  PR wires Cosmos in. Deferred because Cosmos against a single model wouldn't demonstrate real
  orchestration value, and it's a second substantial chunk of work (new provider, image
  changes, Cosmos configuration) best reviewed on its own.
- SCD Type 2 historization for customers — that belongs to the gold `dim_customer` model (via a
  dbt snapshot), not to silver. `stg_customer` is current-state-only, one row per customer.

## Anti-goals

- Don't let "prove the pattern" become "build it twice" — the mechanics decided here (dbt
  project layout, incremental merge/dedup pattern, CI wiring, secret handling) must be reusable
  as-is by every later silver model, not Customer-specific one-offs.
- Don't add gold-layer logic (currency conversion, segment rules, aggregation) into this
  silver model. Per `docs/architecture.md`'s layer rules, enrichment belongs in silver, business
  logic belongs in gold, and segment/territory are already final values set upstream by the
  bootstrap/simulator — silver just carries them through typed and deduplicated.

## Constraints

- Secrets only from environment variables, never committed (`CLAUDE.md`). Databricks
  credentials for CI go into encrypted GitHub Actions repo secrets, not into any workflow file
  or `.env*` committed to the repo.
- `CLAUDE.md`: Python 3.11+, `uv`-managed dependencies, `ruff`, `pytest`; SQL via `sqlfluff`
  (Databricks dialect); dbt models snake_case, `stg_` (silver) / `dim_`, `fact_` (gold)
  prefixes; repo layout already names `dbt/` with `models/silver`, `models/gold`, `snapshots`,
  `tests`.
- Bronze is append-only and untyped: every ERPNext bronze table (including `Customer`) has the
  shape `name`, `modified`, `docstatus`, a `VARIANT` column `raw`, plus `_ingested_at`,
  `_source`, `_batch_id` (`docs/databricks-setup.md`, `docs/extraction-and-bronze.md`). The
  actual customer fields (`customer_name`, `territory`, `customer_group`, etc.) are inside
  `raw` and must be pulled out with `parse_json`/`:field` access, not plain columns.
- Dedup rule already decided in `docs/extraction-and-bronze.md`: when two bronze rows for the
  same `name` share the same `modified`, the tiebreak is the row with the greater
  `_ingested_at` (it picks the more complete record from a later, fuller reload).
- Layer rule already decided in `docs/architecture.md`: silver removes drafts and cancellations
  (`docstatus` 2 = cancelled, per `CLAUDE.md`), types columns, dedupes, and is loaded by
  incremental merge (insert new, update changed) — one model per source entity.
- Databricks connection details already exist as env vars (`DATABRICKS_HOST`,
  `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_CATALOG`), used today by the loaders.
  The dbt profile reuses these (via `env_var()` in `profiles.yml`), rather than inventing a
  second credential scheme.
- Databricks Free Edition's SQL warehouse is zero-cost serverless compute
  (`docs/databricks-setup.md`), which is why running dbt for real in CI was judged acceptable —
  no cost risk, only a secrets-handling one, and GitHub Actions does not expose secrets to
  workflows triggered by pull requests from forks.
- CI reads from the real, shared `bronze` schema — there is one bronze, not a duplicated or
  seeded one per environment, per `CLAUDE.md`'s "one catalog with schemas bronze, silver, gold
  (plus `ci` for CI runs)". Only the *write target* (`ci` schema) is isolated. This means
  `stg_customer`'s tests must tolerate real, known-messy bronze data: the legacy Customer rows
  documented in `docs/extraction-and-bronze.md` that an earlier, buggy extractor loaded with
  only 10 of 53 fields and `docstatus` left `NULL` (kept deliberately, as bronze history, not
  deleted). A schema test that assumes `docstatus` is always `0`/`1`/`2` will fail against real
  data; account for the `NULL` case explicitly rather than discovering it as a CI failure.

## Decisions already made (don't re-ask)

1. **Vertical slice, not big-bang.** This PR: dbt project + `stg_customer` + CI. Breadth
   (remaining silver models, then gold) comes in follow-up PRs.
2. **Dependency placement:** `dbt-core` and `dbt-databricks` live in their own, independent
   `uv` project at `dbt/pyproject.toml`/`dbt/uv.lock` (separate `.venv`, separate resolution from
   the root project) — not the main `pyproject.toml`/`uv.lock`, and not the `[dependency-groups]
   dev` group either. **Revised during implementation:** the original reasoning ("dbt doesn't
   ship an aggressive global constraints file like Airflow did") is true but turned out not to
   matter — `uv lock` failed for real: dbt-databricks (including its latest release, 1.13.0)
   pins `databricks-sdk<0.118.0` and `databricks-sql-connector<4.4.1`, while this project's own
   loaders already require `databricks-sdk>=0.157.0` and `databricks-sql-connector>=4.8.0`, with
   no overlapping range. A different mechanism than ADR 19's constraints-file conflict, same
   practical effect. Isolating dbt into its own `uv` project (invoked via `uv run --directory
   dbt ...`) avoids it without downgrading the root project's Databricks library versions.
   - When Cosmos is wired in (a later PR), `dbt-core`/`dbt-databricks` also get duplicated into
     `docker/airflow/Dockerfile`'s existing minimal pip layer (the same way `pandas`/`pyarrow`/
     `databricks-sql-connector` already are, per ADR 19), because that image isn't a `uv`
     project and can't read either lockfile. `astronomer-cosmos` itself goes in that image
     only, never in a `pyproject.toml` — not part of this PR, noted here only so the later PR
     doesn't re-litigate it.
3. **CI runs dbt for real, against a new `ci` schema.** Not mocked, unlike the Python test
   suite. The `ci` schema is created once, by the user, via the Databricks SQL editor (same
   provisioning pattern as `bronze`/`silver`/`gold` in `docs/databricks-setup.md`) — not
   something CI creates itself.
   - **CI uses a second, narrower-scoped Databricks PAT, not the existing pipeline one.** The
     existing PAT (used by the loaders to write bronze) stays as-is. A second PAT, under the
     same integration user, is provisioned specifically for CI, with Unity Catalog `GRANT`
     statements restricting what that use can do: `SELECT` on `bronze`, full rights on `ci`,
     nothing on `silver`/`gold`. Reasoning: if the CI secret ever leaked, the blast radius
     should be "can mess with the throwaway `ci` schema," not "can write production bronze."
     Free Edition's lack of service principals/account-level admin (`docs/databricks-setup.md`)
     doesn't block this — Unity Catalog schema-level `GRANT`s are a separate mechanism and are
     still available. The exact `GRANT` statements are the builder's call (for the user to run
     once in the Databricks SQL editor, same as other one-time provisioning DDL); the new PAT
     itself is created by the user in the Databricks UI and stored as a new, distinctly-named
     GitHub Actions secret (not overwriting the existing `DATABRICKS_TOKEN`-equivalent secret).
4. **`stg_customer` is current-state-only.** No SCD Type 2 in silver; that's a gold-layer
   concern via a dbt snapshot, for a later PR.

## What's left to the builder

- Exact column list for `stg_customer` (the builder's call, constrained to cover at minimum
  what `docs/data-model.md`'s `dim_customer` will eventually need: the ERPNext `name` as
  customer id, `customer_name`, `territory`, `customer_group`, plus `modified` and the bronze
  metadata columns needed for incremental merge/dedup).
- The exact dbt incremental merge config (`unique_key`, `incremental_strategy`, how the dedup
  tiebreak is expressed in SQL — e.g. `ROW_NUMBER()` over `modified` desc, `_ingested_at` desc).
- `profiles.yml` structure and target names (e.g. `dev` targeting `silver`, `ci` targeting
  `ci`), and exactly which `env_var()` calls back each field.
- Which dbt schema tests to write beyond the obvious (`unique`/`not_null` on the customer id).
- The new doc's exact filename and structure (something documenting how to run dbt locally,
  mirroring the style of `docs/extraction-and-bronze.md`).
- Whether any new ADR entries are needed in `docs/design-decisions.md` for the two decisions
  above (dependency placement, CI hitting real Databricks) — likely yes, following the
  project's existing ADR pattern, but the exact numbering/wording is the builder's call.
- `sqlfluff` configuration specifics for the Databricks dialect (a new `.sqlfluff` config file
  if one doesn't already exist).
