# Phase 10 Part 2: Remaining dbt Silver Models — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 5 silver models still missing after Phase 10 Part 1 (`stg_customer` only), so every bronze table has a typed, deduped, cancellation-filtered silver counterpart, ready for gold to consume.

**Architecture:** Each model follows `stg_customer.sql`'s exact shape: incremental materialization, `merge` strategy, a `rank → filter rank = 1` CTE for deduplication (tiebreak on recency), and (where the source doctype is submittable) a `post_hook` that deletes cancelled rows after merge. Sales Invoice and Purchase Invoice are each flattened to line-item grain in a single model (header fields repeated per line), rather than split into separate header/item models — this matches `fact_sales`/`fact_purchases`' own grain directly, so gold needs no extra join.

**Tech Stack:** dbt-core on Databricks (`dbt-databricks` adapter), Databricks SQL `VARIANT` type and its `:` path-accessor / cast syntax, dbt unit tests (`given`/`expect` YAML).

**Spec:** `docs/data-model.md` (gold grain and source-to-target mapping — the authoritative field list), `docs/extraction-and-bronze.md` (bronze table shapes, bronze verification counts), `docs/design-decisions.md` ADR 16–18 and 23 (bronze VARIANT shape, keyset pagination/watermark overlap, `incoming_rate` stability, CI isolation), `dbt/models/silver/stg_customer.sql` and `dbt/models/silver/_silver__models.yml` (the working precedent every task reuses), plus the decisions recorded below that aren't written down anywhere else yet.

## Global Constraints

- **Silver naming stays `stg_<entity>`** (singular entity, no source prefix) — matches `CLAUDE.md` and the already-merged `stg_customer`, not `docs/conventions.md`'s undocumented-in-practice `stg_<source>__<entity>` form. Task 1 fixes the stale line in `conventions.md`.
- **Dedup tiebreak:** `row_number() over (partition by <unique_key> order by modified desc, _ingested_at desc)`, filter `row_num = 1` — identical to `stg_customer`. For `stg_exchange_rate`, which has no `modified` field, tiebreak is `_ingested_at desc` alone (FRED's own extractor docstring: "silver keeps the latest version of each date").
- **Cancellation filter:** `post_hook="delete from {{ this }} where docstatus = 2"` for every submittable ERPNext doctype (Item, Sales Invoice, Purchase Invoice) — except **Stock Ledger Entry, which uses `where is_cancelled = 1`**. Confirmed against real bronze data: every one of its 1,536,572 rows has `docstatus = 1` (there is no `docstatus = 2` at all for this doctype); the real cancellation signal is its own `is_cancelled` flag, set when the originating invoice is cancelled. A `docstatus = 2` filter here would silently filter nothing and let 2,518 cancelled stock movements through.
- **`docstatus IS NULL` rows are never filtered** — they're legacy incomplete bronze loads (`extraction-and-bronze.md`, "Field completeness"), not drafts, and `stg_customer`'s own test already pins this. Every new model's cancellation test must check `docstatus = 2` is excluded while `docstatus IS NULL` survives (not applicable to `stg_exchange_rate`, which has no `docstatus`).
- **Line-item explosion** (Sales/Purchase Invoice only): `lateral view posexplode(cast(b.raw:items as array<variant>)) as line_idx, item`, then `item:field::type` for each line field. `line_idx` (0-based array position) becomes half of the model's composite `unique_key`. This assumes Databricks VARIANT→`ARRAY<VARIANT>` casting works as documented and that ERPNext's child-table array order is stable across re-fetches of the same document version — both unverified until the first real `dbt run`; Task 3's first step is running it against real bronze data specifically to confirm this before writing its unit tests.
- **FRED's `"."` placeholder** (US holidays, no observation) becomes SQL `NULL` in `stg_exchange_rate`, not `0` or an error. Forward-filling to a usable rate is a **gold-layer** join rule (`data-model.md`: "the most recent earlier rate"), not silver's job — silver stays a thin typed copy of bronze.
- **PR scope:** all 5 models land in one PR (branch `feature/dbt-silver-remaining-models`), mirroring how Part 1 bundled scaffold + one model — each task below is still its own commit, so the PR reviews as 5 self-contained diffs plus a docs fix.
- **File structure:** each model gets its own schema/test YAML file (`_silver__<entity>.yml`) rather than growing one shared file — `_silver__models.yml` (singular, from Part 1) is renamed to `_silver__customer.yml` for consistency in Task 1. `_silver__sources.yml` gains one new `tables:` entry per task, as that task's model needs it.

## Review Focus

- **FRED's `"."` placeholder reaching a numeric column uncast** — a `cast('.' as double)` without the explicit `case when` guard raises at query time in Databricks, rather than producing a clean `NULL`; Task 5 tests this directly.
- **Stock Ledger Entry's inverted cancellation signal** — the one model that does *not* use `docstatus = 2` is the easiest one to "fix" back to the wrong pattern later; Task 2's test pins `is_cancelled = 1` exclusion explicitly, with a comment in the SQL explaining why.
- **Legacy `docstatus IS NULL` rows silently dropped** — any model whose filter is written as `docstatus = 1` (submitted-only) instead of `docstatus IS NULL OR docstatus != 2` repeats the bug `stg_customer` already had to avoid; every ERPNext-sourced task's test suite re-proves this.
- **Missing optional line-item fields** (`incoming_rate` is absent on non-return, non-stock lines per `test_return_uses_return_series_and_incoming_rate_for_stock_items`) — a `::double` cast on a key that doesn't exist in a VARIANT must yield `NULL`, not fail; Task 3's test suite includes a line with no `incoming_rate`.
- **Incremental merge key collisions on re-submitted invoices** — if an invoice is amended/resubmitted and its line count changes, `line_idx` values can realign to different physical lines across versions. Out of scope for this PR (ERPNext invoices here are never amended, only cancelled-and-replaced with a new document number per `docs/bootstrap-rules.md`'s rules), but flagged here rather than silently assumed safe.

---

### Task 1: `stg_item` + naming/file-structure cleanup

**Files:**
- Create: `dbt/models/silver/stg_item.sql`
- Create: `dbt/models/silver/_silver__item.yml`
- Rename: `dbt/models/silver/_silver__models.yml` → `dbt/models/silver/_silver__customer.yml`
- Modify: `dbt/models/silver/_silver__sources.yml` (add `erpnext_item` table)
- Modify: `docs/conventions.md:17` (fix the silver naming row to match `stg_<entity>`)

**Interfaces:**
- Consumes: `source('bronze', 'erpnext_item')` (`name`, `modified`, `docstatus`, `raw` VARIANT with `item_name`, `item_group`, `is_stock_item`)
- Produces: `stg_item(item_id, item_name, item_group, is_stock_item, modified, docstatus, _ingested_at)` — Task 3's `stg_sales_invoice` and Task 4's `stg_purchase_invoice` will later join on `item_id` (not built in this task, just the column name they'll expect).

- [ ] **Step 1: Fix `docs/conventions.md`**

Change line 17's silver row from `stg_<source>__<entity>` / `silver.stg_erpnext__sales_invoice_item` to `stg_<entity>` / `silver.stg_sales_invoice`, matching `stg_customer` and `CLAUDE.md`.

- [ ] **Step 2: Rename the Part 1 schema file**

```bash
git mv dbt/models/silver/_silver__models.yml dbt/models/silver/_silver__customer.yml
```

- [ ] **Step 3: Add the `erpnext_item` source**

In `_silver__sources.yml`, add under the existing `bronze` source's `tables:`:

```yaml
      - name: erpnext_item
```

- [ ] **Step 4: Write the failing unit tests in `_silver__item.yml`**

```yaml
version: 2

models:
  - name: stg_item
    columns:
      - name: item_id
        tests:
          - unique
          - not_null
      - name: modified
        tests:
          - not_null

unit_tests:
  - name: test_tiebreak_by_ingested_at_when_modified_ties
    model: stg_item
    overrides:
      macros:
        is_incremental: false
    given:
      - input: source('bronze', 'erpnext_item')
        format: sql
        rows: |
          select 'ITEM-TIE' as name,
                 '2024-01-01 00:00:00.000000' as modified,
                 1 as docstatus,
                 parse_json('{"item_name":"Old Reload","item_group":"Kitchen & Dining","is_stock_item":1}') as raw,
                 cast('2024-01-01T00:00:00Z' as timestamp) as _ingested_at
          union all
          select 'ITEM-TIE' as name,
                 '2024-01-01 00:00:00.000000' as modified,
                 1 as docstatus,
                 parse_json('{"item_name":"New Reload","item_group":"Kitchen & Dining","is_stock_item":1}') as raw,
                 cast('2024-01-02T00:00:00Z' as timestamp) as _ingested_at
    expect:
      rows:
        - {item_id: "ITEM-TIE", item_name: "New Reload"}

  - name: test_cancelled_item_excluded_but_null_docstatus_kept
    model: stg_item
    overrides:
      macros:
        is_incremental: false
    given:
      - input: source('bronze', 'erpnext_item')
        format: sql
        rows: |
          select 'ITEM-CANCEL' as name,
                 '2024-01-01 00:00:00.000000' as modified,
                 2 as docstatus,
                 parse_json('{"item_name":"Cancelled Item","item_group":"Kitchen & Dining","is_stock_item":1}') as raw,
                 cast('2024-01-01T00:00:00Z' as timestamp) as _ingested_at
          union all
          select 'ITEM-NULL' as name,
                 '2024-01-01 00:00:00.000000' as modified,
                 cast(null as int) as docstatus,
                 parse_json('{"item_name":"Legacy Null Docstatus","item_group":"Candles & Lighting","is_stock_item":0}') as raw,
                 cast('2024-01-01T00:00:00Z' as timestamp) as _ingested_at
    expect:
      rows:
        - {item_id: "ITEM-NULL", item_name: "Legacy Null Docstatus"}
```

Note: the cancelled-item row is expected to survive the `is_incremental: false` compile of the model itself (the `post_hook` only runs on a real `dbt run`, not inside a unit test's compiled `SELECT`) — this test therefore only proves the dedup/selection logic, not the delete. That mirrors how `stg_customer`'s own `assert_stg_customer_excludes_cancelled.sql` (a singular test, not a unit test) is what actually proves the `post_hook` works end to end. Step 6 below adds the equivalent singular test for `stg_item`.

- [ ] **Step 5: Run the unit tests to verify they fail**

Run: `cd dbt && uv run dbt test --select stg_item`
Expected: FAIL (`stg_item` does not exist yet)

- [ ] **Step 6: Implement `stg_item.sql`**

```sql
{{
    config(
        materialized='incremental',
        unique_key='item_id',
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where docstatus = 2"
    )
}}

with ranked as (

    select
        b.name as item_id,
        b.raw:item_name::string as item_name,
        b.raw:item_group::string as item_group,
        b.raw:is_stock_item::int as is_stock_item,
        b.modified,
        b.docstatus,
        b._ingested_at,
        row_number() over (
            partition by b.name
            order by b.modified desc, b._ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_item') }} as b
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

)

select
    item_id,
    item_name,
    item_group,
    is_stock_item,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
```

- [ ] **Step 7: Add the singular cancellation test**

Create `dbt/tests/assert_stg_item_excludes_cancelled.sql`, copying `assert_stg_customer_excludes_cancelled.sql`'s shape with `stg_item`/`item_id` in place of `stg_customer`/`customer_id`.

- [ ] **Step 8: Run the full model build and tests**

Run: `cd dbt && uv run dbt build --select stg_item`
Expected: PASS (model runs, both unit tests and the singular test pass)

- [ ] **Step 9: Lint**

Run: `cd dbt && uv run sqlfluff lint models/silver/stg_item.sql`
Expected: no violations (fix and re-run if any)

- [ ] **Step 10: Commit**

```bash
git add dbt/models/silver/stg_item.sql dbt/models/silver/_silver__item.yml dbt/models/silver/_silver__sources.yml dbt/models/silver/_silver__customer.yml dbt/tests/assert_stg_item_excludes_cancelled.sql docs/conventions.md
git commit -m "feat: add stg_item silver model"
```

---

### Task 2: `stg_stock_ledger_entry`

**Files:**
- Create: `dbt/models/silver/stg_stock_ledger_entry.sql`
- Create: `dbt/models/silver/_silver__stock_ledger_entry.yml`
- Modify: `dbt/models/silver/_silver__sources.yml` (add `erpnext_stock_ledger_entry` table)

**Interfaces:**
- Consumes: `source('bronze', 'erpnext_stock_ledger_entry')` (`name`, `modified`, `docstatus`, `raw` VARIANT with `item_code`, `posting_date`, `voucher_type`, `actual_qty`, `qty_after_transaction`, `warehouse`, `incoming_rate`, `stock_value_difference`, `is_cancelled`)
- Produces: `stg_stock_ledger_entry(entry_id, item_id, posting_date, voucher_type, actual_qty, qty_after_transaction, warehouse, incoming_rate, stock_value_difference, is_cancelled, modified, docstatus, _ingested_at)`

- [ ] **Step 1: Add the `erpnext_stock_ledger_entry` source**

Same shape as Task 1 Step 3, new table name.

- [ ] **Step 2: Write the failing unit tests**

`_silver__stock_ledger_entry.yml`, following the same `version: 2` / `models:` / `unit_tests:` shape as `_silver__item.yml`. Include:
- `test_tiebreak_by_ingested_at_when_modified_ties` (same pattern as Task 1).
- `test_is_cancelled_flag_is_preserved_even_though_docstatus_is_always_1` — two input rows, both `docstatus = 1`, one `is_cancelled = 1` and one `is_cancelled = 0` (use `raw:is_cancelled` as part of the JSON payload: `parse_json('{"item_code":"85123A","posting_date":"2025-11-15","voucher_type":"Sales Invoice","actual_qty":-6,"qty_after_transaction":100,"warehouse":"Stores - MHG","incoming_rate":1.57,"stock_value_difference":-9.42,"is_cancelled":1}')` for the cancelled one); `expect` both rows present in the model's own output (this test proves the column is read correctly, not that the `post_hook` deletes it — same caveat as Task 1 Step 4).

- [ ] **Step 3: Run the unit tests to verify they fail**

Run: `cd dbt && uv run dbt test --select stg_stock_ledger_entry`
Expected: FAIL

- [ ] **Step 4: Implement `stg_stock_ledger_entry.sql`**

```sql
{{
    config(
        materialized='incremental',
        unique_key='entry_id',
        incremental_strategy='merge',
        -- Stock Ledger Entry never carries docstatus = 2: every row observed in bronze is
        -- docstatus = 1, because an SLE inherits submission state from its source invoice
        -- rather than being submitted/cancelled itself. is_cancelled is the real flag,
        -- set when that source invoice is cancelled (see ADR 23's sibling, ADR 18).
        post_hook="delete from {{ this }} where is_cancelled = 1"
    )
}}

with ranked as (

    select
        b.name as entry_id,
        b.raw:item_code::string as item_id,
        b.raw:posting_date::date as posting_date,
        b.raw:voucher_type::string as voucher_type,
        b.raw:actual_qty::decimal(18, 4) as actual_qty,
        b.raw:qty_after_transaction::decimal(18, 4) as qty_after_transaction,
        b.raw:warehouse::string as warehouse,
        b.raw:incoming_rate::decimal(18, 4) as incoming_rate,
        b.raw:stock_value_difference::decimal(18, 4) as stock_value_difference,
        b.raw:is_cancelled::int as is_cancelled,
        b.modified,
        b.docstatus,
        b._ingested_at,
        row_number() over (
            partition by b.name
            order by b.modified desc, b._ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_stock_ledger_entry') }} as b
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

)

select
    entry_id,
    item_id,
    posting_date,
    voucher_type,
    actual_qty,
    qty_after_transaction,
    warehouse,
    incoming_rate,
    stock_value_difference,
    is_cancelled,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
```

- [ ] **Step 5: Add the singular cancellation test**

Create `dbt/tests/assert_stg_stock_ledger_entry_excludes_cancelled.sql`: same shape as `assert_stg_customer_excludes_cancelled.sql`, but comparing on `is_cancelled = 1` instead of `docstatus = 2`.

- [ ] **Step 6: Run the full model build and tests**

Run: `cd dbt && uv run dbt build --select stg_stock_ledger_entry`
Expected: PASS

- [ ] **Step 7: Lint**

Run: `cd dbt && uv run sqlfluff lint models/silver/stg_stock_ledger_entry.sql`
Expected: no violations

- [ ] **Step 8: Commit**

```bash
git add dbt/models/silver/stg_stock_ledger_entry.sql dbt/models/silver/_silver__stock_ledger_entry.yml dbt/models/silver/_silver__sources.yml dbt/tests/assert_stg_stock_ledger_entry_excludes_cancelled.sql
git commit -m "feat: add stg_stock_ledger_entry silver model"
```

---

### Task 3: `stg_sales_invoice` (line grain)

**Files:**
- Create: `dbt/models/silver/stg_sales_invoice.sql`
- Create: `dbt/models/silver/_silver__sales_invoice.yml`
- Modify: `dbt/models/silver/_silver__sources.yml` (add `erpnext_sales_invoice` table)

**Interfaces:**
- Consumes: `source('bronze', 'erpnext_sales_invoice')` (`name`, `modified`, `docstatus`, `raw` VARIANT with `customer`, `posting_date`, `due_date`, `is_return`, `outstanding_amount`, and a child array `items[]` of `{item_code, qty, net_amount, incoming_rate?}`)
- Produces: `stg_sales_invoice(sales_invoice_id, line_idx, customer_id, posting_date, due_date, is_return, outstanding_amount, item_id, qty, net_amount, incoming_rate, modified, docstatus, _ingested_at)`

- [ ] **Step 1: Confirm the VARIANT array explode syntax against real bronze data**

Before writing any dbt code, run this once in the Databricks SQL editor (this is a **Databricks** query, not something `dbt` runs):

```sql
select
    b.name,
    line_idx,
    item:item_code::string as item_id,
    item:qty::int as qty,
    item:net_amount::decimal(18, 4) as net_amount,
    item:incoming_rate::decimal(18, 4) as incoming_rate
from erp_analytics.bronze.erpnext_sales_invoice as b
lateral view posexplode(cast(b.raw:items as array<variant>)) as line_idx, item
where b.name = (select name from erp_analytics.bronze.erpnext_sales_invoice limit 1)
```

If `cast(... as array<variant>)` fails or `posexplode` doesn't behave as expected, note the working syntax here and use it for Step 4 instead — the rest of this task's logic (columns, filters, tests) doesn't change, only the explode mechanics would.

- [ ] **Step 2: Add the `erpnext_sales_invoice` source**

Same shape as Task 1 Step 3.

- [ ] **Step 3: Write the failing unit tests**

`_silver__sales_invoice.yml`, covering:
- `test_tiebreak_by_ingested_at_when_modified_ties` — two versions of the same invoice/line (`SINV-TIE`, one line), newer `_ingested_at` wins.
- `test_cancelled_invoice_excluded_but_null_docstatus_kept` — same two-row shape as Task 1 Step 4, adapted to invoice fields.
- `test_line_without_incoming_rate_keeps_null` — one invoice with two lines in its `items` array, one with `incoming_rate` present (a return of a stock item) and one without it (a non-stock line); `expect` the second line's `incoming_rate` to be `null`, not a cast failure. Example `raw` payload:
  `parse_json('{"customer":"17850","posting_date":"2025-11-15","due_date":"2025-12-15","is_return":0,"outstanding_amount":15.30,"items":[{"item_code":"85123A","qty":6,"net_amount":15.30,"incoming_rate":1.57},{"item_code":"D","qty":1,"net_amount":0.0}]}')`
  `expect.rows` checks `line_idx: 1, item_id: "D", incoming_rate: null`.

- [ ] **Step 4: Run the unit tests to verify they fail**

Run: `cd dbt && uv run dbt test --select stg_sales_invoice`
Expected: FAIL

- [ ] **Step 5: Implement `stg_sales_invoice.sql`**

```sql
{{
    config(
        materialized='incremental',
        unique_key=['sales_invoice_id', 'line_idx'],
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where docstatus = 2"
    )
}}

with exploded as (

    select
        b.name as sales_invoice_id,
        line_idx,
        b.raw:customer::string as customer_id,
        b.raw:posting_date::date as posting_date,
        b.raw:due_date::date as due_date,
        b.raw:is_return::int as is_return,
        b.raw:outstanding_amount::decimal(18, 2) as outstanding_amount,
        item:item_code::string as item_id,
        item:qty::decimal(18, 4) as qty,
        item:net_amount::decimal(18, 2) as net_amount,
        item:incoming_rate::decimal(18, 4) as incoming_rate,
        b.modified,
        b.docstatus,
        b._ingested_at
    from {{ source('bronze', 'erpnext_sales_invoice') }} as b
    lateral view posexplode(cast(b.raw:items as array<variant>)) as line_idx, item
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

), ranked as (

    select
        *,
        row_number() over (
            partition by sales_invoice_id, line_idx
            order by modified desc, _ingested_at desc
        ) as row_num
    from exploded

)

select
    sales_invoice_id,
    line_idx,
    customer_id,
    posting_date,
    due_date,
    is_return,
    outstanding_amount,
    item_id,
    qty,
    net_amount,
    incoming_rate,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
```

- [ ] **Step 6: Add the singular cancellation test**

Create `dbt/tests/assert_stg_sales_invoice_excludes_cancelled.sql`, same shape as `assert_stg_customer_excludes_cancelled.sql`.

- [ ] **Step 7: Add the cost-of-sales cross-check from ADR 18**

Create `dbt/tests/assert_stg_sales_invoice_cost_matches_stock_ledger.sql`: joins `stg_sales_invoice` (stock items only, `qty * incoming_rate`) to `stg_stock_ledger_entry` on invoice id / item, asserting the two amounts match within a small tolerance — this is the test ADR 18 says should exist to catch a future divergence, and Task 2 already built the model it joins to.

- [ ] **Step 8: Run the full model build and tests**

Run: `cd dbt && uv run dbt build --select stg_sales_invoice`
Expected: PASS

- [ ] **Step 9: Lint**

Run: `cd dbt && uv run sqlfluff lint models/silver/stg_sales_invoice.sql`
Expected: no violations

- [ ] **Step 10: Commit**

```bash
git add dbt/models/silver/stg_sales_invoice.sql dbt/models/silver/_silver__sales_invoice.yml dbt/models/silver/_silver__sources.yml dbt/tests/assert_stg_sales_invoice_excludes_cancelled.sql dbt/tests/assert_stg_sales_invoice_cost_matches_stock_ledger.sql
git commit -m "feat: add stg_sales_invoice silver model"
```

---

### Task 4: `stg_purchase_invoice` (line grain)

**Files:**
- Create: `dbt/models/silver/stg_purchase_invoice.sql`
- Create: `dbt/models/silver/_silver__purchase_invoice.yml`
- Modify: `dbt/models/silver/_silver__sources.yml` (add `erpnext_purchase_invoice` table)

**Interfaces:**
- Consumes: `source('bronze', 'erpnext_purchase_invoice')` (`name`, `modified`, `docstatus`, `raw` VARIANT with `supplier`, `posting_date`, and a child array `items[]` of `{item_code, qty, net_amount}`)
- Produces: `stg_purchase_invoice(purchase_invoice_id, line_idx, supplier_id, posting_date, item_id, qty, net_amount, modified, docstatus, _ingested_at)`

- [ ] **Step 1: Add the `erpnext_purchase_invoice` source**

Same shape as Task 1 Step 3.

- [ ] **Step 2: Write the failing unit tests**

`_silver__purchase_invoice.yml`, covering `test_tiebreak_by_ingested_at_when_modified_ties` and `test_cancelled_invoice_excluded_but_null_docstatus_kept`, same two patterns as Task 3, adapted to this model's (simpler, no `incoming_rate`) fields.

- [ ] **Step 3: Run the unit tests to verify they fail**

Run: `cd dbt && uv run dbt test --select stg_purchase_invoice`
Expected: FAIL

- [ ] **Step 4: Implement `stg_purchase_invoice.sql`**

Same structure as Task 3's `stg_sales_invoice.sql`, with these differences: `unique_key=['purchase_invoice_id', 'line_idx']`; no `is_return`, `due_date`, `outstanding_amount`, or `incoming_rate` columns; header key is `b.raw:supplier::string as supplier_id` instead of `customer_id`; line columns are `item:item_code::string as item_id`, `item:qty::decimal(18, 4) as qty`, `item:net_amount::decimal(18, 2) as net_amount`.

- [ ] **Step 5: Add the singular cancellation test**

Create `dbt/tests/assert_stg_purchase_invoice_excludes_cancelled.sql`.

- [ ] **Step 6: Run the full model build and tests**

Run: `cd dbt && uv run dbt build --select stg_purchase_invoice`
Expected: PASS

- [ ] **Step 7: Lint**

Run: `cd dbt && uv run sqlfluff lint models/silver/stg_purchase_invoice.sql`
Expected: no violations

- [ ] **Step 8: Commit**

```bash
git add dbt/models/silver/stg_purchase_invoice.sql dbt/models/silver/_silver__purchase_invoice.yml dbt/models/silver/_silver__sources.yml dbt/tests/assert_stg_purchase_invoice_excludes_cancelled.sql
git commit -m "feat: add stg_purchase_invoice silver model"
```

---

### Task 5: `stg_exchange_rate`

**Files:**
- Create: `dbt/models/silver/stg_exchange_rate.sql`
- Create: `dbt/models/silver/_silver__exchange_rate.yml`
- Modify: `dbt/models/silver/_silver__sources.yml` (add `fred_exchange_rates` table)

**Interfaces:**
- Consumes: `source('bronze', 'fred_exchange_rates')` (`series_id`, `observation_date`, `raw` VARIANT with `value` — `"."` on US holidays — `_ingested_at`; no `modified`, no `docstatus`)
- Produces: `stg_exchange_rate(observation_date, usd_per_gbp, series_id, _ingested_at)` — later gold work (not this PR) joins `fact_sales.posting_date` etc. to this on `observation_date`, forward-filling gaps.

- [ ] **Step 1: Add the `fred_exchange_rates` source**

In `_silver__sources.yml`, add a second `sources:` entry (different source name, since this isn't `bronze`'s ERPNext family in spirit, though it lives in the same `bronze` schema — follow whatever `sources:` block shape keeps `source('bronze', 'fred_exchange_rates')` resolvable; if `_silver__sources.yml`'s existing single `bronze` source block already covers any table in that schema, just add `fred_exchange_rates` under its `tables:` list like the others).

- [ ] **Step 2: Write the failing unit tests**

```yaml
version: 2

models:
  - name: stg_exchange_rate
    columns:
      - name: observation_date
        tests:
          - unique
          - not_null

unit_tests:
  - name: test_holiday_placeholder_becomes_null
    model: stg_exchange_rate
    overrides:
      macros:
        is_incremental: false
    given:
      - input: source('bronze', 'fred_exchange_rates')
        format: sql
        rows: |
          select 'DEXUSUK' as series_id,
                 '2024-01-01' as observation_date,
                 parse_json('{"value":"."}') as raw,
                 cast('2024-01-02T00:00:00Z' as timestamp) as _ingested_at
    expect:
      rows:
        - {observation_date: "2024-01-01", usd_per_gbp: null}

  - name: test_later_ingestion_wins_when_no_modified_field_exists
    model: stg_exchange_rate
    overrides:
      macros:
        is_incremental: false
    given:
      - input: source('bronze', 'fred_exchange_rates')
        format: sql
        rows: |
          select 'DEXUSUK' as series_id,
                 '2024-01-02' as observation_date,
                 parse_json('{"value":"1.2650"}') as raw,
                 cast('2024-01-03T00:00:00Z' as timestamp) as _ingested_at
          union all
          select 'DEXUSUK' as series_id,
                 '2024-01-02' as observation_date,
                 parse_json('{"value":"1.2699"}') as raw,
                 cast('2024-01-10T00:00:00Z' as timestamp) as _ingested_at
    expect:
      rows:
        - {observation_date: "2024-01-02", usd_per_gbp: 1.2699}
```

- [ ] **Step 3: Run the unit tests to verify they fail**

Run: `cd dbt && uv run dbt test --select stg_exchange_rate`
Expected: FAIL

- [ ] **Step 4: Implement `stg_exchange_rate.sql`**

```sql
{{
    config(
        materialized='incremental',
        unique_key='observation_date',
        incremental_strategy='merge'
    )
}}

with ranked as (

    select
        b.series_id,
        cast(b.observation_date as date) as observation_date,
        case
            when b.raw:value::string = '.' then null
            else b.raw:value::decimal(18, 6)
        end as usd_per_gbp,
        b._ingested_at,
        row_number() over (
            partition by b.observation_date
            order by b._ingested_at desc
        ) as row_num
    from {{ source('bronze', 'fred_exchange_rates') }} as b
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

)

select
    observation_date,
    usd_per_gbp,
    series_id,
    _ingested_at
from ranked
where row_num = 1
```

- [ ] **Step 5: Run the full model build and tests**

Run: `cd dbt && uv run dbt build --select stg_exchange_rate`
Expected: PASS

- [ ] **Step 6: Lint**

Run: `cd dbt && uv run sqlfluff lint models/silver/stg_exchange_rate.sql`
Expected: no violations

- [ ] **Step 7: Commit**

```bash
git add dbt/models/silver/stg_exchange_rate.sql dbt/models/silver/_silver__exchange_rate.yml dbt/models/silver/_silver__sources.yml
git commit -m "feat: add stg_exchange_rate silver model"
```

---

### Task 6: Full-project verification and docs

**Files:**
- Modify: `docs/data-model.md` (if any column names drifted from the mapping table during implementation — e.g. `item_code` → `item_id` — reconcile the table)
- Modify: `docs/ai-context/HANDOFF.md` (overwrite with the session's final state, per `CLAUDE.md`'s rule)

- [ ] **Step 1: Run the whole dbt project**

Run: `cd dbt && uv run dbt build`
Expected: all 6 silver models (`stg_customer` plus the 5 new ones) run and pass, no test failures

- [ ] **Step 2: Lint everything**

Run: `cd dbt && uv run sqlfluff lint models/`
Expected: no violations

- [ ] **Step 3: Confirm CI is green**

Push the branch, open the PR, wait for `ci.yml` to pass (it runs `dbt build` for real against the isolated `ci` schema per ADR 23 — this is the first real test of that pipeline against more than one model).

- [ ] **Step 4: Reconcile docs and hand off**

Update `docs/data-model.md`'s source-to-target mapping table only if any column name actually ended up different from what's written there today; update `HANDOFF.md` with the final state (models shipped, PR number, any open items — e.g. the line-item explode syntax risk from Task 3 Step 1, once resolved one way or the other, is worth recording either as "confirmed working" or as a note for whichever syntax ended up being used).
