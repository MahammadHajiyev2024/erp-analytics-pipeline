# ERP Analytics Pipeline

End-to-end analytics pipeline: ERPNext REST API → Airflow → Databricks medallion lakehouse → dbt → Power BI.

> **Status:** Work in progress. Currently in Phase 0 (environment setup).

## Overview

This project simulates the data platform of a fictional company. Business data lives in an
ERP system (ERPNext), and a custom ELT pipeline extracts it through the ERPNext REST API,
loads it into a Databricks lakehouse, transforms it through bronze, silver, and gold layers
with dbt, and serves it to Power BI dashboards. ERPNext and Airflow run in Docker containers,
so the whole environment can be reproduced with a single command.

*Business case and key questions: coming soon.*

## Architecture

*Diagram coming soon.*

| Layer | Tool |
|---|---|
| Source system | ERPNext, seeded with real retail data |
| Extraction and loading | Custom Python extractors and loaders |
| Orchestration | Apache Airflow |
| Containerization | Docker and Docker Compose |
| Warehouse | Databricks (bronze, silver, gold) |
| Transformation and data quality | dbt |
| Reporting | Power BI |
| CI/CD | GitHub Actions |

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

Requirements: [Git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/), and, from Phase 1
onward, [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/MahammadHajiyev2024/erp-analytics-pipeline.git
cd erp-analytics-pipeline
uv sync
cp .env.example .env   # then fill in your own values
```

## Roadmap

- [x] Phase 0: Environment setup
- [ ] Phase 1: ERPNext source system in Docker
- [ ] Phase 2: Load historical data
- [ ] Phase 3: Business activity simulator
- [ ] Phase 4: Databricks warehouse setup
- [ ] Phase 5: Extraction and bronze layer
- [ ] Phase 6: dbt silver and gold layers
- [ ] Phase 7: Airflow orchestration in Docker
- [ ] Phase 8: CI/CD with GitHub Actions
- [ ] Phase 9: Power BI dashboards
- [ ] Phase 10: Documentation and demo

## Data sources

- Historical sales data: [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) (CC BY 4.0)
- Economic indicators: [FRED](https://fred.stlouisfed.org/), Federal Reserve Bank of St. Louis