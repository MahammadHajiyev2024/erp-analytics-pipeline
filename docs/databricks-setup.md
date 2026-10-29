# Databricks Lakehouse Setup

Setup notes and configuration for the `erp_analytics` lakehouse environment on Databricks Free Edition.

## 1. Environment and Metastore
- **Tier:** Databricks Free Edition (Serverless compute, 2X-Small SQL Warehouse).
- **Region:** AWS `us-east-2` (Ohio).
- **Data Residency Note:** In a production setting for a UK business subject to UK GDPR, data would reside in a UK or EU region (`eu-west-2`). For this project, anonymized data residing in `us-east-2` provides zero-cost compute.
- **Access:** Pipeline authentication uses a Personal Access Token (PAT) configured in `.env`. Service principals and account-level administration are not supported in Free Edition.

## 2. Structure
- **Catalog:** `erp_analytics`
- **Schemas:**
  - `bronze`: Raw append-only Delta tables and landing files.
  - `silver`: Cleaned, typed, deduplicated tables (managed by dbt).
  - `gold`: Star schema conformed dimensions and facts (managed by dbt).
- **Volume:** `/Volumes/erp_analytics/bronze/landing` (staging point for extractor `.jsonl` files).

## 3. Provisioning DDL
```sql
CREATE CATALOG IF NOT EXISTS erp_analytics;
USE CATALOG erp_analytics;

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE VOLUME IF NOT EXISTS bronze.landing
  COMMENT 'Landing volume for raw JSON Lines extractor dumps';
```

## 4. Bronze table shape

Every ERPNext bronze table shares the same untyped shape (`name`, `modified`, `docstatus`, a
`VARIANT` column `raw`, plus the `_ingested_at` / `_source` / `_batch_id` metadata columns); see
[design decision 16](design-decisions.md#16-ingestion-to-bronze-via-landing-volume-and-copy-into)
for why and how it is loaded with `COPY INTO`.
