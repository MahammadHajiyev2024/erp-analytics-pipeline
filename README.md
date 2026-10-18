# ERP Analytics Pipeline

End-to-end analytics pipeline: ERPNext REST API → Airflow → Databricks medallion lakehouse → dbt → Power BI.

> **Status:** Work in progress. Requirements and environment setup are complete; currently in Phase 1 (Architecture and Design).

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

## Business case

**Maple Home & Gift Ltd** is a UK-based online wholesaler of home décor and giftware, selling
everything from candle holders and kitchenware to Christmas decorations and party goods. It has
no physical shops: customers order online, and most are small retailers and gift shops buying in
bulk to resell, alongside a smaller number of individual buyers. The company serves over 5,900
customers in 43 countries, most of them in the United Kingdom and the rest of Europe. Its busiest
season is autumn, with sales peaking every November ahead of Christmas. Maple keeps its books in
British pounds and reports its performance in US dollars to its US-based parent company.

*Maple Home & Gift is fictional. Its sales history comes from the real, anonymized transactions
of a UK online retailer (the UCI Online Retail II dataset), with dates shifted forward. Its costs,
its parent company, and all activity after the historical period are simulated.*

## Stakeholders, KPIs, and scope

The dashboards serve four stakeholders: the Managing Director, Sales Manager, Inventory Manager,
and Finance Manager. Key KPIs include net revenue (in GBP and USD), gross margin, year-over-year
growth, average order value, days of stock cover, return rate, and accounts receivable.

Data is refreshed in a daily batch. Real-time data, forecasting, and full tax compliance are out of scope.

Detailed questions, KPI definitions, assumptions, scope, and constraints are in
[requirements](docs/requirements.md).


## Architecture


*Diagram coming soon.*

The reasoning behind each choice is in [design decisions](docs/design-decisions.md).

## Project structure

```
bootstrap/    One-time load of historical data into ERPNext
simulator/    Generates daily business activity in ERPNext
extractors/   Pull data from the ERPNext and FRED APIs
loaders/      Write raw data to the Databricks bronze layer
tests/        Unit tests for the Python code
docs/         Architecture and design decisions
```

## Getting started

Requirements: [Git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/), and, from Phase 4
onward, [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/MahammadHajiyev2024/erp-analytics-pipeline.git
cd erp-analytics-pipeline
uv sync
cp .env.example .env   # then fill in your own values (on Windows: Copy-Item .env.example .env)
```

## Roadmap

- [x] Phase 0: Requirements analysis
- [ ] Phase 1: Architecture and design
- [x] Phase 2: Environment setup
- [ ] Phase 3: Continuous integration
- [ ] Phase 4: Source system (ERPNext)
- [ ] Phase 5: Bootstrap historical data
- [ ] Phase 6: Business activity simulator
- [ ] Phase 7: Databricks lakehouse setup
- [ ] Phase 8: Extraction and bronze layer
- [ ] Phase 9: dbt silver and gold layers
- [ ] Phase 10: Airflow orchestration
- [ ] Phase 11: Power BI reporting
- [ ] Phase 12: Documentation and demo

## Data sources

- Historical sales data: [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) (CC BY 4.0)
- Exchange rates (GBP to USD): [FRED](https://fred.stlouisfed.org/), Federal Reserve Bank of St. Louis
