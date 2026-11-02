# ERP Analytics Pipeline

[![CI](https://github.com/MahammadHajiyev2024/erp-analytics-pipeline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MahammadHajiyev2024/erp-analytics-pipeline/actions/workflows/ci.yml)

End-to-end analytics pipeline: ERPNext REST API → Airflow → Databricks medallion lakehouse → dbt → Power BI.

> **Status:** Work in progress. Phases 0 to 9 are complete: requirements, architecture, environment setup, continuous integration, the ERPNext source system, two years of verified historical data, a business activity simulator that keeps the company trading daily, a Databricks lakehouse, the extraction/bronze layer, and Airflow orchestration. Phase 10's dbt Silver layer (6 staging models) is also done. Next is Phase 10's Gold layer (the star schema).

## Overview

This project simulates the data platform of Maple Home & Gift Ltd, a fictional UK-based
online wholesaler of home décor and giftware, modeled on a real UK online retailer whose
anonymized transactions (the UCI Online Retail II dataset) form the company's sales history.
Business data lives in an ERP system (ERPNext), and a custom ELT pipeline extracts it through
the ERPNext REST API, loads it into a Databricks lakehouse, transforms it through bronze,
silver, and gold layers with dbt, and serves it to Power BI dashboards. ERPNext and Airflow
run in Docker containers, so the whole environment can be reproduced with a single command.

The company keeps its books in British pounds (GBP), matching the source data, while
management reporting is in US dollars (USD), converted with daily exchange rates from FRED,
as multinational companies do.

## Business Case

**Maple Home & Gift Ltd** is a UK-based online wholesaler of home décor and giftware, selling
everything from candle holders and kitchenware to Christmas decorations and party goods. It has
no physical shops: customers order online, and most are small retailers and gift shops buying in
bulk to resell, alongside a smaller number of individual buyers. The company serves over 5,900
customers in 43 countries, most of them in the United Kingdom and the rest of Europe. Its busiest
season is fall, with sales peaking every November ahead of Christmas. Maple keeps its books in
British pounds and reports its performance in US dollars to its US-based parent company.

*Maple Home & Gift is fictional. Its sales history comes from the real, anonymized transactions
of a UK online retailer (the UCI Online Retail II dataset), with dates shifted forward. Its costs,
its parent company, and all activity after the historical period are simulated*.

## Stakeholders, KPIs, and Scope

The dashboards serve four stakeholders: the Managing Director, Sales Manager, Inventory Manager,
and Finance Manager. Key KPIs include net revenue (in GBP and USD), gross margin, year-over-year
growth, average order value, days of stock cover, return rate, and accounts receivable.

Data is refreshed in a daily batch. Real-time data, forecasting, and full tax compliance are out of scope.

Detailed questions, KPI definitions, assumptions, scope, and constraints are in
[requirements](docs/requirements.md).


## Architecture

The design follows **Separation of Concerns**: each layer and component has a single responsibility.

![Architecture of the ERP analytics pipeline](docs/architecture.drawio.svg)

The reasoning behind each choice is in [design decisions](docs/design-decisions.md).

Naming rules for tables, columns, and code are in [conventions](docs/conventions.md).

The star schema, with the grain of each table, is in [data model](docs/data-model.md).

## Project Structure

```
bootstrap/    One-time load of historical data into ERPNext
simulator/    Generates daily business activity in ERPNext
extractors/   Pull data from the ERPNext and FRED APIs
loaders/      Write raw data to the Databricks bronze layer
tests/        Unit tests for the Python code
docs/         Architecture and design decisions
common/       Code shared by several parts, such as the ERPNext API client
```

## Getting Started

Requirements: [Git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/), and, from Phase 4
onward, [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/MahammadHajiyev2024/erp-analytics-pipeline.git
cd erp-analytics-pipeline
uv sync
cp .env.example .env   # then fill in your own values (on Windows: Copy-Item .env.example .env)
```

To start ERPNext (the first start creates the site, which takes a few minutes):

```bash
docker compose -f docker/erpnext/compose.yaml --env-file .env up -d
```

ERPNext then runs at http://localhost:8080. Log in as `Administrator` with the
`ERPNEXT_ADMIN_PASSWORD` from your `.env`. To stop it:

```bash
docker compose -f docker/erpnext/compose.yaml --env-file .env stop
```
First-time setup (company, fiscal year, and the pipeline's read-only user)
is described in [ERPNext setup](docs/erpnext-setup.md).

## Notable Engineering Decisions

Full reasoning for every decision is in [`docs/design-decisions.md`](docs/design-decisions.md)
(ADRs). A few worth a closer look:

- **ADR 23 — CI runs as a second, deliberately under-privileged Databricks user, not the
  pipeline's own account.** Least privilege in practice: a leaked CI secret can touch a
  throwaway schema, not real data. Getting there took two false starts (a new "scoped token"
  feature that a required connector backend silently couldn't read) before finding the actual
  cause — documented including the dead ends, not just the fix.
- **ADR 17 — Keyset pagination with a watermark overlap for incremental extraction.** Measured,
  not assumed: offset pagination silently skips rows when a background job rewrites old records
  mid-page; paging by `modified` instead of the indexed `name` column measured ~11s vs. ~0.1s per
  page on 1.5M rows.
- **ADR 18 — Investigated a data-correctness red flag and ruled it out with evidence.** ERPNext
  was silently rewriting old stock records in the background. Rather than assume it was harmless
  or over-correct, compared all 69,965 affected rows and confirmed the field revenue math
  depends on never changed, then added a dbt test so a real future divergence gets caught.
- **ADR 22 — Found a real dependency conflict via a failed `uv lock`, not a guess**, and
  restructured the project (dbt in its own `uv` project) rather than force an unsafe downgrade.

## Roadmap

- [x] Phase 0: Requirements analysis
- [x] Phase 1: Architecture and design
- [x] Phase 2: Environment setup
- [x] Phase 3: Continuous integration
- [x] Phase 4: Source system (ERPNext)
- [x] Phase 5: Bootstrap historical data
- [x] Phase 6: Business activity simulator
- [x] Phase 7: Databricks lakehouse setup
- [x] Phase 8: Extraction and bronze layer
- [x] Phase 9: Airflow orchestration
- [ ] Phase 10: dbt silver and gold layers
- [ ] Phase 11: Power BI reporting
- [ ] Phase 12: Documentation and demo

## Data Sources

- Historical sales data: [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) (CC BY 4.0)
- Exchange rates (GBP to USD): [FRED](https://fred.stlouisfed.org/), Federal Reserve Bank of St. Louis
