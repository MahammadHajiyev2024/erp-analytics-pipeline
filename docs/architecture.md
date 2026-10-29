# Architecture

How data flows through the platform, and the rules each layer follows. The diagram is in the
[README](../README.md#architecture).

## Design principles

**Separation of concerns:** every component has one responsibility, so each can be understood,
tested, and changed independently.

- **Layers:** bronze stores raw data, silver cleans it, and gold applies business logic.
- **Extraction and loading:** extractors only read from APIs; loaders only write to the lakehouse.
- **Simulation and extraction:** the simulator plays the business; the extractors play the data
  engineer.
- **Orchestration and logic:** Airflow decides when things run; the logic lives in Python modules
  and dbt models.
- **Code and configuration:** credentials and settings live in environment variables, not in code.
- **Transformation and presentation:** dbt builds the data; Power BI presents it.

## Data flow

1. **Bootstrap** loads historical data into ERPNext once; the **simulator** adds new business
   activity every day. Both write through the ERPNext REST API.
2. **Extractors** read new and changed records from the ERPNext REST API, plus daily exchange
   rates from FRED. **Loaders** append them to the bronze layer in Databricks.
3. **dbt** transforms bronze into silver (cleaned) and silver into gold (star schema).
4. **Power BI** imports the gold tables into a semantic model and dashboards.
5. **Airflow** runs steps 1 to 3 daily, in order, with retries and alerts.

## Layer rules

| | Bronze | Silver | Gold |
|---|---|---|---|
| **Definition** | Raw data, exactly as received from the sources | Cleaned and standardized data | Business-ready data |
| **Objective** | Traceability, debugging, and reprocessing | Prepare reliable data for modeling | Serve reporting and analytics |
| **Object type** | Delta tables | Delta tables (dbt models) | Delta tables (dbt models and snapshots) |
| **Load method** | Incremental append, using `modified` watermarks | Incremental merge (insert new, update changed) | Rebuilt each run; snapshots track history |
| **Transformations** | None, apart from metadata columns (`_ingested_at`, `_source`, `_batch_id`) | Typing, deduplication, flattening line items, removing drafts and cancellations, standardizing codes, enriching (product categories) | Integration, currency conversion, business rules (segments, margins), aggregation |
| **Data modeling** | None (same shape as the source) | One model per source entity | Star schema (facts and dimensions) |
| **Tools** | Python extractors and loaders | dbt | dbt |
| **Audience** | Data engineers | Data engineers and analysts | Analysts and business users |

**Rule of thumb:** enrichment (adding descriptive attributes) belongs in silver; business logic
(rules the business could change, such as segments and margins) belongs in gold.
