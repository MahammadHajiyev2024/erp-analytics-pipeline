# Naming conventions

Rules for naming everything in the project, so names are predictable and self-explanatory.

## Lakehouse structure

| Level | Name | Purpose |
|---|---|---|
| Catalog | `erp_analytics` | Everything for this project |
| Schemas | `bronze`, `silver`, `gold` | One schema per medallion layer |

## Tables

| Layer | Pattern | Example |
|---|---|---|
| Bronze | `<source>_<entity>` | `bronze.erpnext_sales_invoice`, `bronze.fred_exchange_rates` |
| Silver | `stg_<source>__<entity>` | `silver.stg_erpnext__sales_invoice_item` |
| Gold dimensions | `dim_<entity>` | `gold.dim_customer` |
| Gold facts | `fact_<process>` | `gold.fact_sales` |

- Entity names are **singular** (`customer`, not `customers`).
- In silver, the **double underscore** separates the source from the entity, so names stay
  readable when either part contains single underscores. This follows dbt's style guide.

## Columns

| Kind | Rule | Example |
|---|---|---|
| All columns | lowercase snake_case | `posting_date` |
| Business keys | `<entity>_id` | `customer_id`, `invoice_id` |
| Surrogate keys (gold) | `<entity>_key` | `customer_key` |
| Dates | `_date` suffix | `posting_date` |
| Timestamps | `_at` suffix | `modified_at` |
| True/false flags | `is_` or `has_` prefix | `is_return` |
| Money | currency suffix | `net_amount_gbp`, `net_amount_usd` |
| Counts | `_count` suffix | `invoice_count` |
| Pipeline metadata | leading underscore | `_ingested_at`, `_source`, `_batch_id` |

- A key has the **same name in every table**, so joins are obvious: `fact_sales.customer_key`
  joins to `dim_customer.customer_key`.
- The leading underscore marks technical columns added by the pipeline, separating them
  from business data.

## Python

| Kind | Rule | Example |
|---|---|---|
| Modules and functions | snake_case | `extract_customers()` |
| Classes | PascalCase | `ErpNextClient` |
| Constants | UPPER_SNAKE_CASE | `PAGE_SIZE` |

## Git

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `build:`, `ci:`, `chore:`, `style:`.
  - Branch names describe the work: `feature/customer-extractor`, `fix/pagination-limit`.
