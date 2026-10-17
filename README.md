# ERP Analytics Pipeline

End-to-end analytics pipeline: ERPNext REST API → Airflow → Databricks medallion lakehouse → dbt → Power BI.

> **Status:** Work in progress. Environment setup is complete; currently in Phase 0 (requirements analysis).

## Overview

This project simulates the data platform of a fictional UK-based online giftware wholesaler,
modeled on a real UK online retailer whose anonymized transactions (the UCI Online Retail II
dataset) form the company's sales history.
Business data lives in an ERP system (ERPNext), and a custom ELT pipeline extracts it through
the ERPNext REST API, loads it into a Databricks lakehouse, transforms it through bronze,
silver, and gold layers with dbt, and serves it to Power BI dashboards. ERPNext and Airflow
run in Docker containers, so the whole environment can be reproduced with a single command.

The company keeps its books in British pounds (GBP), matching the source data, while
management reporting is in US dollars (USD), converted with daily exchange rates from FRED,
as multinational companies do.

*Business case and key questions: coming soon.*

## Architecture

*Diagram coming soon.*

| Layer | Tool |
|---|---|
| Source system | ERPNext, seeded with real retail data |
| Extraction and loading | Custom Python extractors and loaders |
| Orchestration | Apache Airflow |
| Containerization | Docker and Docker Compose |
| Lakehouse | Databricks (bronze, silver, gold) |
| Transformation and data quality | dbt |
| Reporting | Power BI |
| CI/CD | GitHub Actions |
| Python environment and packages | uv |
| Code quality | ruff, pre-commit |

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

- [ ] Phase 0: Requirements analysis
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
