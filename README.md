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

### Stakeholders and key questions

| Stakeholder | Key questions |
|---|---|
| **Managing Director** | How are revenue and profit trending, in GBP and USD? How does performance compare with last year? Which countries and customer segments contribute most? |
| **Sales Manager** | Who are the top customers, and who is buying less? Which products sell best, and which are bought together? How large are orders, and how often do customers reorder? |
| **Inventory Manager** | Which products are close to running out? Which aren't selling and are tying up stock? How does demand change by season? |
| **Finance Manager** | What is the gross margin by category? How much do returns cost? How much do customers owe, and how much is overdue? |

### KPIs

| KPI | Definition | Data basis |
|---|---|---|
| Net revenue | Sum of invoice line net amounts, with returns subtracted | Real |
| Net revenue (USD) | Net amount × the GBP-to-USD rate on each posting date | Real, plus FRED rates |
| Gross profit | Net revenue − cost of goods sold | Assumed item costs |
| Gross margin % | Gross profit ÷ net revenue | Assumed costs and categories |
| Year-over-year growth % | Change in net revenue versus the same period last year | Real, once the full history is loaded |
| Customer revenue change % | A customer's revenue in the last 3 months versus the 3 months before | Mostly simulated |
| Product pair frequency | Number of invoices containing both products of a pair | Real |
| Average order value | Net revenue ÷ number of sales invoices | Real |
| Repeat purchase rate | Share of customers with more than one order in a period | Real, with longer history |
| Days of stock cover | Stock on hand ÷ average daily units sold (last 30 days) | Simulated stock |
| Slow-moving stock value | Value of stock with no sales in the last 90 days | Simulated stock |
| Seasonal index | A month's units sold ÷ the average month's units sold | Real, with 12+ months |
| Return rate % | Value of returns ÷ value of sales before returns | Real |
| Accounts receivable and overdue % | Unpaid invoice amounts, and the share past due | Simulated payments |

All KPIs follow the same rules: revenue excludes tax, only submitted documents count, dates are
posting dates, and returns are subtracted from revenue.

**Assumptions.** The source data has no costs, product categories, customer segments, stock
levels, or payments. Item costs and categories are derived by stated rules, customers are
segmented into Wholesale and Retail by order size, and stock and payments are simulated. Every
KPI that depends on an assumption is labeled as such.

### Scope and constraints

| Area | Decision |
|---|---|
| Data freshness | Daily batch updates |
| History | November 2011 first; extended to the full dataset (December 2009 to December 2011) once the pipeline works |
| Currency | Books in GBP; reporting in GBP and USD |
| Access | Sales views can be restricted by territory (row-level security) |
| Infrastructure | Runs on a 16 GB laptop with free services (Databricks Free Edition, Power BI Desktop) |

**Out of scope:** real-time data, manufacturing, HR and payroll, forecasting and machine learning,
full VAT and international tax compliance, and multiple companies or warehouses.
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
