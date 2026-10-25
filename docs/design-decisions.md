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

**Decision:** The bootstrap loads November 2011 first, then the full dataset once the
pipeline is proven.
**Why:** A fast first build on a 16 GB laptop, then real history for year-over-year and
seasonal analysis.
**Alternative:** Loading everything up front, which delays the first working pipeline.

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

#### 16. Ingestion to bronze via landing volume and COPY INTO
**Decision:** Extractors write raw records as JSON Lines (.jsonl) files into a Databricks Unity Catalog Volume (`erp_analytics.bronze.landing`), which are then ingested into bronze Delta tables using Databricks `COPY INTO`.
**Why:**
- **Built-in Idempotency:** `COPY INTO` tracks loaded files natively, preventing duplicate ingestion if a pipeline batch is re-run.
- **Compute Efficiency:** Bulk loading one file via `COPY INTO` on a 2X-Small warehouse consumes far fewer compute credits and runtime than running thousands of individual `INSERT` statements.
- **Auditability and Replayability:** Raw responses remain archived in the landing volume, allowing the bronze layer to be rebuilt without re-querying ERPNext.
- **Decoupled Architecture:** Network uploads from Python and warehouse compute run independently; warehouse pauses do not interrupt extraction.
- **JSON Lines Representation:** Preserves the exact nested payloads returned by the ERPNext REST API until dbt flattens and types them in the silver layer.
**Alternative:** Direct row-by-row `INSERT` statements over SQL, which is slow for large datasets (over 1M rows), consumes daily quotas, and provides no raw file archive.
**Implementation Note (SDK vs SQL Connector):**Volume uploads use the Databricks SDK (`WorkspaceClient.files.upload`) rather than SQL `PUT` commands. The SDK uploads directly via the Databricks control plane without requiring the SQL warehouse to be running, preserving the Free Edition daily compute quota. The warehouse is started only when executing `COPY INTO` via `databricks-sql-connector`.
