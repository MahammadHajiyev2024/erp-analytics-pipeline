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

## 4. Create the integration user

The pipeline reads ERPNext as a dedicated, read-only user (see design decision 7).

1. **Role:** in **Role List**, add a role named `Pipeline Reader` with **Desk Access** ticked.
2. **Permissions:** in **Role Permissions Manager**, add a level 0 rule for `Pipeline Reader`
   on each document type below, with only **Read** ticked. **Only if Creator** stays unticked.

   | Document type | Used for |
   |---|---|
   | Sales Invoice | `fact_sales`, `fact_receivables` |
   | Purchase Invoice | `fact_purchases` |
   | Stock Ledger Entry | `fact_stock_movements` |
   | Customer, Customer Group | `dim_customer` |
   | Item, Item Group | `dim_product` |
   | Supplier | `dim_supplier` |

   Child tables such as Sales Invoice Item need no rule of their own; they are readable
   whenever their parent document is.
3. **User:** in **User List**, add `pipeline@mhg.local` with first name `Pipeline` and no
   welcome email. On the **Roles & Permissions** tab, leave **Role Profile** empty and tick
   only `Pipeline Reader`.
4. **API key:** on the user's page, click **Generate Keys**. Copy the key and secret into
   `ERPNEXT_API_KEY` and `ERPNEXT_API_SECRET` in `.env`. The secret is shown only once.
5. **Check:** run the connection check from the repository root:

   ```bash
   uv run python -m extractors.erpnext
   ```

   It must connect as `pipeline@mhg.local`, read Sales Invoice and Customer, and be refused
   for Journal Entry.

## 5. Create the bootstrap user

The bootstrap and the simulator write to ERPNext as a separate user, so scripts never use
the Administrator account.

1. **User:** in **User List**, add `bootstrap@mhg.local` with first name `Bootstrap` and no
   welcome email. On the **Roles & Permissions** tab, leave **Role Profile** empty and tick
   only **Accounts User**, **Stock User**, **Item Manager**, **Sales Master Manager**, and
   **Purchase Master Manager**. Check the roles again after the first save.
2. **API key:** on the **Settings** tab, click **Generate Keys**. Copy the key and secret
   into `ERPNEXT_BOOTSTRAP_API_KEY` and `ERPNEXT_BOOTSTRAP_API_SECRET` in `.env`.
3. **Check:** `uv run python -m extractors.erpnext` must also print
   `Bootstrap user: bootstrap@mhg.local`.

These standard roles give more than the bootstrap strictly needs, but only business
permissions: no user management, permission changes, or system settings.

## 6. Create fiscal years and VAT templates

Done once as Administrator, before the bootstrap.

1. **Fiscal years:** in **Fiscal Year List**, add 2023, 2024, and 2025, each from 1 January
   to 31 December, with Maple Home & Gift Ltd in the **Companies** table. The setup
   wizard already created 2026. The history starts on 28 November 2023 (design decision
   14), and ERPNext refuses invoices outside a fiscal year.
2. **UK VAT:** the setup wizard creates **United Kingdom Tax - MHG** (On Net Total, account
   **VAT - MHG**, 20%). Use it unchanged for invoices to the United Kingdom.
3. **Export VAT:** in **Sales Taxes and Charges Template List**, add **Zero-Rated Export**
   with one row: On Net Total, account **VAT - MHG**, rate 0. Use it for invoices to all
   other countries. Neither template is the default; the bootstrap always sets one.

## Troubleshooting

**`Bind for 0.0.0.0:8080 failed: port is already allocated`.** Another program, or
another ERPNext setup, uses port 8080. Stop the other setup. If no container uses the
port, quit and reopen Docker Desktop to release it.

**`frontend` keeps restarting with `host not found in upstream "backend:8000"`.** The
container lost its network connection, usually after a failed start. Recreate it:

```bash
docker compose -f docker/erpnext/compose.yaml --env-file .env up -d --force-recreate frontend
```

**The connection check fails with `401 UNAUTHORIZED` although `.env` is correct.** An older
`ERPNEXT_API_KEY` or `ERPNEXT_API_SECRET` is already set in the terminal, and python-dotenv
never overwrites existing variables. Remove them and run the check again (PowerShell):

```powershell
Remove-Item env:ERPNEXT_API_KEY, env:ERPNEXT_API_SECRET -ErrorAction SilentlyContinue
```

**The connection check fails with `403 Insufficient Permission`.** The role is missing from
the user, or **Read** is not ticked in its rules. Fix that, then clear ERPNext's permission
cache:

```bash
docker compose -f docker/erpnext/compose.yaml --env-file .env exec backend bench --site frontend clear-cache
```
