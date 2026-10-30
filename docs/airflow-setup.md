# Airflow setup

How to bring up the project's Airflow stack (Phase 9 orchestration). This is a second,
independent Docker stack alongside ERPNext's -- see design decision 6.

## 1. Generate the secrets Airflow needs

Airflow's metadata database needs a password, and two internal secrets protect
communication between its own components (not ERPNext/Databricks credentials -- those
stay exactly as they are). Generate them once and add them to `.env`:

```bash
# AIRFLOW_FERNET_KEY -- encrypts sensitive values Airflow stores in its own database
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# AIRFLOW_JWT_SECRET -- signs the internal tokens Airflow's own components use to talk
# to each other (its new Task Execution API, since Airflow 3.0)
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

Set in `.env`: `AIRFLOW_DB_PASSWORD`, `AIRFLOW_FERNET_KEY`, `AIRFLOW_JWT_SECRET`,
`AIRFLOW_WWW_USER_USERNAME` (defaults to `admin`), `AIRFLOW_WWW_USER_PASSWORD`. See
`.env.example`.

## 2. Start the stack

```bash
docker compose --env-file .env up -d
```

No `-f` flag needed -- this is the one `docker-compose.yml` at the repository root, so
bare `docker compose` commands act on it. ERPNext's stack always needs
`-f docker/erpnext/compose.yaml` explicitly, since it lives under `docker/erpnext/`.

The first start builds the image, runs Postgres migrations, and creates the admin user
(`airflow-init` exits 0 when done):

```bash
docker compose --env-file .env ps -a
```

## 3. Open the UI

<http://localhost:8082> (or your `AIRFLOW_PORT`), log in with
`AIRFLOW_WWW_USER_USERNAME` / `AIRFLOW_WWW_USER_PASSWORD`. `AIRFLOW__CORE__LOAD_EXAMPLES`
is off, so the only DAG listed should be `_smoke_test`.

**New DAGs start paused** (Airflow's default) -- toggle `_smoke_test` on in the UI, or
trigger a single manual run with the ▶ button without unpausing it.

## 4. Verify

```bash
docker compose exec airflow-scheduler airflow dags list-import-errors
docker compose exec airflow-scheduler airflow dags test _smoke_test 2026-01-01
```

The first command should print nothing (no import errors). The second runs the DAG
immediately, outside the schedule, and should show the `hello` task succeeding with its
log line in the output.

## Why this is two Docker stacks, not one

Airflow's containers reach ERPNext over its **published host port**
(`ERPNEXT_URL=http://localhost:8080` normally) -- exactly like every extractor, pytest,
and your browser already do. They are deliberately *not* joined to ERPNext's internal
`frappe_network`: that would make Airflow's connectivity depend on ERPNext's internal
service names, an unrelated coupling to a system this stack doesn't own.

The one consequence: inside a Linux container on Docker Desktop for Windows, `localhost`
means *the container itself*, not your machine. `docker-compose.yml` overrides
`ERPNEXT_URL` to `http://host.docker.internal:${ERPNEXT_PORT:-8080}` for exactly this
reason -- if a task's ERPNext calls fail with a connection error even though `curl
http://localhost:8080` works fine from your own terminal, this is almost always why.

## Why Airflow isn't in `pyproject.toml`

`apache-airflow` and its dependencies live only inside `docker/airflow/Dockerfile`,
installed against Airflow's own constraints file. Resolving it into the main project's
`uv.lock` risks forcing version conflicts with the main project's own pins for a service
dependency, not a pipeline dependency. See the Dockerfile's own comments, and
[ADR 6](design-decisions.md#6-airflow-for-orchestration-in-docker).

## Resource reminder (16 GB RAM laptop)

This adds roughly 1-1.5 GB of idle RAM on top of ERPNext's own ~2-3 GB. Stop **both**
stacks at the end of a session -- data is kept, `start`/`up -d` resumes:

```bash
docker compose --env-file .env stop
docker compose -f docker/erpnext/compose.yaml --env-file .env stop
```

## Troubleshooting

**A task fails trying to reach ERPNext, but `curl http://localhost:8080` works from your
terminal.** See "Why this is two Docker stacks" above -- the task ran inside a container,
where `localhost` isn't your machine.

**`airflow-init` exits non-zero.** Check its logs:
`docker compose logs airflow-init`. The most likely cause is a missing or malformed
secret in `.env` (`AIRFLOW_DB_PASSWORD`, `AIRFLOW_FERNET_KEY`, `AIRFLOW_JWT_SECRET`,
`AIRFLOW_WWW_USER_PASSWORD` are all required, with no defaults, for exactly this reason
-- Airflow should fail loudly on startup rather than run with a weak or blank secret).

**Port 8082 is already in use.** Set a different `AIRFLOW_PORT` in `.env`. (Port 8080 is
ERPNext's; port 8081 is reserved for the separate test ERPNext instance used in
simulator development.)

**`docker compose up` fails during the image build with a pip `ResolutionImpossible`
error on a package from `docker/airflow/requirements.txt`.** The Dockerfile no longer
pins against Airflow's `--constraint` file -- that file freezes exact versions for every
package Airflow was tested against at release time, including ones Airflow doesn't
actually depend on (pandas, pyarrow, python-dotenv, databricks-sql-connector are only
imported by our own code), so it fell behind `pyproject.toml`'s floors and rejected an
otherwise-fine install. If this error reappears after bumping a floor in
`requirements.txt`, it means Airflow's own actual dependency ranges (not the frozen
constraints snapshot) now conflict -- rebuild with `docker compose build --no-cache
airflow-init` to see the real error.

## What's next

PR2 adds the real DAG (`dags/erp_pipeline.py`), removing `_smoke_test.py`. This doc gets
the task graph and verification steps for that DAG at the same time.
