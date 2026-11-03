# Extraction and bronze layer

How Python turns ERPNext and FRED into the bronze layer: which extractor each source uses, the
commands that run them, the shape bronze tables take, and how to replay or verify them. The
design behind keyset pagination and the watermark overlap is in
[design decision 17](design-decisions.md#17-keyset-pagination-with-a-watermark-overlap-for-incremental-extraction).

## Extractors

| Source | Extractor | Why |
|---|---|---|
| Customer, Item, Supplier, Stock Ledger Entry | `extractors/erpnext/listing.py` (generic list-only) | No child tables; the list API returns every field in one page |
| Sales Invoice, Purchase Invoice | `extractors/erpnext/documents.py` (generic document) | Line items only come back on a full-document fetch, so each document needs its own GET |
| FRED GBP→USD rates | `extractors/fred/exchange_rates.py` | A different API entirely: series DEXUSUK, the H.10 noon buying rate, published weekly on Mondays, from 2023-11-01. US holidays carry the value `"."`, kept as received; a 30-day overlap covers late publication. The API key is redacted from both error messages and `urllib3`'s retry logs. |

Both ERPNext extractors share `extractors/watermark.py`: a JSON file (`data/watermarks.json`)
holding, per doctype, `last_modified` (the newest `modified` actually loaded, from the source's
own clock, never the load time) and `last_extracted_at` (informational only).

## Commands

```bash
uv run python -m extractors.erpnext.customer
uv run python -m extractors.erpnext.item
uv run python -m extractors.erpnext.supplier
uv run python -m extractors.erpnext.stock_ledger_entry
uv run python -m extractors.erpnext.sales_invoice
uv run python -m extractors.erpnext.purchase_invoice
uv run python -m extractors.fred.exchange_rates
```

Each extractor writes new and changed records as JSON Lines to
`data/landing/<slug>/<slug>_<UTC timestamp>_<batch id>.jsonl`, first as `.part`, renamed only
once the file is complete; the watermark advances only after that rename, so a failed run
leaves nothing behind to load twice.

To trial an extractor without touching the real watermark or landing folder:

```bash
uv run python -m extractors.erpnext.item --max-records 5000 \
  --output-dir data/scratch/x --watermark-path data/scratch/x_wm.json
```

## Loading to bronze

`loaders/bronze.py` has two steps:

1. **`upload_to_volume(path, volume_dir)`** uploads a landing file to the Databricks volume
   `/Volumes/erp_analytics/bronze/landing` with the Databricks SDK
   (`WorkspaceClient.files.upload`), which needs no running SQL warehouse. It never overwrites:
   a file already there of the same size is skipped, a different size raises.
2. **`load_variant_to_bronze(table, volume_path)`** runs `COPY INTO` to load the file into its
   bronze table, starting the SQL warehouse only for this step. One-line wrappers exist per
   source: `load_customers_to_bronze`, `load_items_to_bronze`, `load_sales_invoices_to_bronze`,
   `load_purchase_invoices_to_bronze`, `load_stock_ledger_entries_to_bronze`,
   `load_suppliers_to_bronze`, `load_fred_exchange_rates_to_bronze`.

`COPY INTO` tracks which files it has already loaded into a table, so running the load again
never reloads a file — dropping the table is the only way to make it reload everything. Landing
files stay in the volume rather than being deleted after loading, so bronze can always be
rebuilt by replaying every file for a table, without re-querying ERPNext.

`data/scratch/run_incremental.py` runs every extractor once, then uploads and loads only the
file each run just wrote — a preview of the daily Airflow DAG (Phase 9).

## Bronze table shape

Every ERPNext bronze table has the same shape: `name STRING`, `modified STRING`,
`docstatus INT`, `raw VARIANT`, plus `_ingested_at TIMESTAMP`, `_source STRING`,
`_batch_id STRING`. `bronze.fred_exchange_rates` uses `series_id` and `observation_date` in
place of the ERPNext keys. See
[design decision 16](design-decisions.md#16-ingestion-to-bronze-via-landing-volume-and-copy-into)
for why the record itself is stored untyped, in `raw`, rather than typed columns.

## Bronze verification (28 October 2026)

Verifying the bronze layer against ERPNext directly, by comparing the latest version of each
`name` in bronze (by `modified`, then `_ingested_at`) with ERPNext's own count:

| Doctype | Bronze (latest version) | Matches ERPNext? |
|---|---|---|
| Customer | 7,306 | Yes |
| Item | 4,861 | Yes |
| Supplier | 9 (verified 2 November 2026, the day it was first extracted) | Yes |
| Sales Invoice | 66,365 submitted + 73 cancelled | Yes |
| Purchase Invoice | 333 submitted + 1 cancelled | Yes |
| Stock Ledger Entry | 1,534,054 active + 2,518 cancelled | Yes (`max(modified)` only, since reposting keeps rewriting it) |

ERPNext has no draft documents. Of the 73 cancelled Sales Invoices, 68 are the simulator's
cancellations and 5 are manual test documents left in ERPNext on purpose (21–23 October 2026,
all cancelled, never counted as real activity): `TEST-RET-001`, `TEST-PAY-SI`, `TEST-PAY-RET`
(none of the three has a `custom_source_invoice`), plus one Purchase Invoice `TEST-PI-001`;
their stock entries are `MAT-SLE-2026-00001` to `-00006`. No `custom_source_invoice` appears on
more than one submitted invoice.

**Field completeness.** The first Customer and Item loads, written by an earlier extractor,
kept only 10 and 18 fields respectively, with `docstatus` left null. All fields the data model
needs were present among them, but bronze must store the whole record raw. Fixed on 28 October
by a full reload with the current list extractor (run against scratch watermark files, leaving
the real watermarks untouched): 7,306 customers with their full 53 fields, 4,861 items with
their full 82 fields. The incomplete old rows were kept rather than deleted, as bronze history;
silver's deduplication tiebreak on `_ingested_at` picks the complete row whenever `modified` is
equal.

**Clock change.** UK clocks went back on 25 October 2026, repeating 01:00–02:00 in `modified`'s
local time (see [Time zones](architecture.md#time-zones)). No documents were created in that
window — the simulator was paused from 21:00 on 24 October to 04:00 on 25 October — so this
particular change did not put any data at risk. The 2-hour overlap stays in place regardless,
for the next UK clock change (29 March 2027).
