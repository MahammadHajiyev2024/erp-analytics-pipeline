# dbt setup

How to work with the project's dbt project (`dbt/`, Phase 10 silver/gold layers). This is the
first vertical slice — one silver model, `stg_customer` — proving the connection, the local
workflow, and CI before the remaining silver models and any gold model are added. See design
decisions 22 and 23 in `design-decisions.md`.

## 1. Why `dbt/` is its own, separate `uv` project

`dbt/pyproject.toml` and `dbt/uv.lock` are independent of the root project's — their own
`.venv`, their own dependency resolution. This isn't the main project's `dev` dependency group:
`dbt-databricks` pins `databricks-sdk`/`databricks-sql-connector` versions older than this
project's loaders already require, so the two can't share one lockfile (ADR 22). Every `dbt`
(and `sqlfluff`, for dbt SQL specifically) command runs with `--directory dbt`, which tells
`uv` to use `dbt/`'s environment for that one command, regardless of where it's invoked from.

## 2. One-time setup

```bash
uv sync --directory dbt
```

Populates `dbt/.venv` with `dbt-core`, `dbt-databricks`, `sqlfluff`, and
`sqlfluff-templater-dbt`. Re-run it whenever `dbt/pyproject.toml`/`dbt/uv.lock` change.

## 3. Targets and environment variables

`dbt/profiles.yml` defines two targets:

| Target | Schema | Used for | Token env var |
|---|---|---|---|
| `dev` | `silver` | local development | `DATABRICKS_TOKEN` |
| `ci`  | `ci`     | CI only            | `DATABRICKS_CI_TOKEN` |

`DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN`, and `DATABRICKS_CATALOG` are
already in `.env.example` — the same ones the loaders use. `DATABRICKS_CI_TOKEN` is the
exception: it's a second, narrowly-scoped PAT (ADR 23) that only ever lives as a GitHub Actions
repo secret, never in a local `.env`.

## 4. Local commands

Run these from the repo root. `dbt` doesn't call `load_dotenv()` the way the Python
loaders do, and plain `uv run` doesn't read `.env` on its own either -- pass `--env-file .env`
explicitly, or the commands below fail with `Env var required but not provided`:

```bash
# Check the connection (prints the resolved schema -- confirm it says silver, not ci, for dev)
uv run --env-file .env --directory dbt dbt debug --profiles-dir . --target dev

# Build the model(s) and run their tests
uv run --env-file .env --directory dbt dbt build --profiles-dir . --target dev

# Run only the unit tests (fast, literal mock data, no bronze/silver tables touched)
uv run --env-file .env --directory dbt dbt test --profiles-dir . --target dev --select test_type:unit

# Lint dbt SQL (Databricks dialect, dbt templater)
uv run --directory dbt sqlfluff lint models/ tests/
```

`dbt debug`/`dbt build`/`dbt test` all connect to the real Databricks warehouse — the same as
running a SQL query by hand. Run them yourself, or confirm first if an agent session is about
to run one.

## 5. Troubleshooting

- **`dbt debug`/`dbt build` fails to connect, but credentials look right.** If you're running
  from Git Bash (not PowerShell or cmd), check the printed `http_path` in the output — Git
  Bash's MSYS layer silently rewrites environment variable values that start with `/` (like
  `DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/...`) into a Windows path (e.g.
  `C:/Program Files/Git/sql/1.0/warehouses/...`) when handing the environment to a native
  Windows process. Fix: either run the command from PowerShell instead, or prefix it with
  `MSYS_NO_PATHCONV=1` in Git Bash.
- **A plain `dbt build` right after adding a new model reports success but ran zero tests.**
  dbt's partial-parse cache (`dbt/target/partial_parse.msgpack`) can carry over a stale state
  from before the model existed. Force a fresh parse once with
  `uv run --directory dbt dbt build --profiles-dir . --target dev --no-partial-parse`.

## 6. CI

CI authenticates as a second, narrowly-granted Databricks user (`mhajiyev17@gmail.com`), not
the integration user the production loaders use -- a leaked CI secret can read `bronze` and
fully use `ci`, but has no access to `silver`/`gold` (ADR 23).

`.github/workflows/ci.yml` runs `uv sync --directory dbt --locked` then
`dbt build --profiles-dir . --target ci --full-refresh`, authenticated with the CI token (ADR
23). `--full-refresh` matters: without it, CI would merge into whatever `ci.stg_customer` was
left over from the last run, so a model change (e.g. a new column) would never get re-tested
against a clean build. One-time setup:

1. Create the `ci` schema once, in the Databricks SQL editor:
   ```sql
   USE CATALOG erp_analytics;
   CREATE SCHEMA IF NOT EXISTS ci;
   ```
2. Invite the second workspace user if it doesn't already exist, and grant it (once):
   ```sql
   GRANT USE CATALOG ON CATALOG erp_analytics TO `<ci-token-user>`;
   GRANT USE SCHEMA, SELECT ON SCHEMA erp_analytics.bronze TO `<ci-token-user>`;
   GRANT USE SCHEMA, CREATE TABLE, SELECT, MODIFY ON SCHEMA erp_analytics.ci TO `<ci-token-user>`;
   ```
   No grants on `silver`/`gold` — that absence is the point. Verify with
   `SHOW GRANTS ON SCHEMA erp_analytics.silver;` (expect nothing for that user).
3. Create that user's token via the API, **not** the "Generate new token" UI dialog --
   the UI's default `autoscope_enabled: true` behavior silently produces a token Thrift can't
   read (ADR 23 has the full story). Call `POST /api/2.0/token/create` with
   `"scopes": []` and `"autoscope_enabled": false` explicitly, authenticating the request with
   any token that user already has (even a broken scoped one works for this one call, since
   the failure is Thrift-specific, not a general API problem).
4. Add `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_CATALOG`, and
   `DATABRICKS_CI_TOKEN` (the token from step 3) as GitHub Actions repo secrets (Settings →
   Secrets and variables → Actions).
