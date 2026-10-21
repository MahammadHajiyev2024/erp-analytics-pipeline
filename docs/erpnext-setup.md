# ERPNext setup

How to set up the project's ERPNext (the source system) from scratch. It takes about
15 minutes, most of it waiting for the site to be created.

## 1. Start ERPNext

Set `ERPNEXT_ADMIN_PASSWORD` and `ERPNEXT_DB_ROOT_PASSWORD` in `.env`, then run from the
repository root:

```bash
docker compose -f docker/erpnext/compose.yaml --env-file .env up -d
```

The first start creates the site. It is finished when the `create-site` container shows
`Exited (0)`:

```bash
docker compose -f docker/erpnext/compose.yaml --env-file .env ps -a
```

Then open http://localhost:8080 and log in as `Administrator` with the
`ERPNEXT_ADMIN_PASSWORD` from `.env`.

## 2. Run the setup wizard

| Screen | Field | Value |
|---|---|---|
| Region | Language | English |
| | Country | United Kingdom |
| | Time zone | Europe/London |
| | Currency | GBP |
| About you | Who are you setting this up for? | My own business |
| | Team size | 11–50 |
| | Industry | Wholesale / Distribution |
| | Current system | Nothing yet - starting fresh |
| | Modules | Accounting, Stock |
| Company | Company name | Maple Home & Gift Ltd |
| | Abbreviation | MHG |
| | Chart of accounts | Standard |
| | Financial year begins on | 01-01-2026 |
| | Demo data | Off |

Demo data must stay off: it would add fake customers and invoices that would flow into
the pipeline. The fiscal year follows the calendar year (see design decision 13). Fiscal
years for the historical data are created by the bootstrap in Phase 5.

## 3. Check the result

- **Company:** Maple Home & Gift Ltd has default currency GBP and country United Kingdom.
- **Fiscal year:** one fiscal year, 2026, from 01-01-2026 to 31-12-2026.
- **Customers:** the customer list is empty.

## Troubleshooting

**`Bind for 0.0.0.0:8080 failed: port is already allocated`.** Another program, or
another ERPNext setup, uses port 8080. Stop the other setup. If no container uses the
port, quit and reopen Docker Desktop to release it.

**`frontend` keeps restarting with `host not found in upstream "backend:8000"`.** The
container lost its network connection, usually after a failed start. Recreate it:

```bash
docker compose -f docker/erpnext/compose.yaml --env-file .env up -d --force-recreate frontend
```
