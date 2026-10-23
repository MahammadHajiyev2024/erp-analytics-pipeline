# Bootstrap rules

How the UCI Online Retail II data becomes Maple Home & Gift's history in ERPNext. The
bootstrap (Phase 5) applies these rules once; the simulator (Phase 6) continues from where
the history ends. Row counts come from `notebooks/01_explore_online_retail.ipynb`.

## Dates

All source dates move forward by exactly 730 weeks (design decision 14). The history runs
from Tuesday 28 November 2023 to Friday 5 December 2025, and every order keeps its
original weekday. Fiscal years 2023, 2024, and 2025 are created before loading; 2026
already exists.

## Cleaning

| Source rows (counted on the raw data) | Treatment |
|---|---|
| 34,335 exact duplicate rows | Removed |
| Non-sales codes: fees (`AMAZONFEE`, `BANK CHARGES`, `CRUK`), adjustments (`ADJUST`, `ADJUST2`, `B`, `M`, in any case), samples (`S`), and tests (`TEST001`, `TEST002`) | Excluded |
| 6,207 rows with a zero or negative price, plus prices below £0.01 (GBP has two decimals) | Excluded |
| About 3,456 negative-quantity rows that are not cancellations | Excluded |
| 5 discount (`D`) rows on normal invoices | Excluded as data errors |
| `DCGS` items and gift vouchers | Kept |

   Stock codes are trimmed of surrounding spaces and converted to uppercase when the source
   is loaded. The same product sometimes appears in both cases (such as `15056BL` and
   `15056bl`), and ERPNext treats names that differ only in case as the same, so 170 codes
   are merged this way.

The rules run in the order above; each sees only the rows the previous rules kept, so
rows with several problems count once, under the first rule that removes them. Result on
the full source (`uv run python -m bootstrap.clean`):

| Step | Rows removed |
|---|---|
| Duplicates | 34,335 |
| Internal codes | 1,504 |
| Zero or negative prices | 6,009 |
| Other negative quantities | 0 (all also had a zero price) |
| Discounts on normal invoices | 5 |
| **Clean rows** | **1,025,518** |

The clean data has 47,374 invoices, 18,322 cancellation rows (the 1,172 fewer than in the
raw data were duplicates or non-sales codes), and 228,688 Guest Customer rows.

## Customers

- **Missing customer ID** (22% of clean rows): the order belongs to a single **Guest
  Customer**, which gets its own segment, **Guest**. Guest orders have a median value of
  £201, closer to wholesale than retail, so they cannot be classified as either.
- **Segments:** a customer whose median order value (sales invoices only) is at least
  **£150** is **Wholesale**, otherwise **Retail**. Order values form a single peak around
  £150–400 with no natural gap, so the threshold is a judgment: an individual rarely
  spends £150 on one order, while a shop restocking usually does. It makes 80% of
  customers Wholesale, matching the business case. Customers with no sales (only
  cancellations) count as Retail.
- **Country:** each customer's most frequent invoice country.

## Products

- **Categories:** each product gets one category (an ERPNext Item Group) from keyword
  rules on its description. Rules are checked in a fixed order and the first match wins,
  so seasonal categories such as Christmas come first. Unmatched products go to
  **Other**, which should stay below about 10–15% of products. The keywords live in a
  file in the repository and are covered by unit tests.
  On the full data, 4,750 products get a category, and 15.0% fall into Other.
- **Service items:** shipping codes (`POST`, `DOT`, `C2`) and discounts become non-stock
  service items named **Shipping** and **Discount**.
- **Costs:** each stock item has one fixed cost: its median selling price multiplied by
  its category's cost ratio, plus a small adjustment of up to about ±5 percentage points
  derived from the stock code. The adjustment is deterministic, so every run produces the
  same costs. Cost ratios aim at gross margins of roughly 40–50%. Shipping passes through
  at cost (no margin); discounts have no cost.
  The resulting average gross margin at typical prices is 44.7%.

## Sales and returns

- **Invoices:** each source invoice becomes a Sales Invoice.
- **Cancellations** (19,494 rows, invoice numbers starting with `C`): become return
  invoices. Discount lines on cancellations become **Discount** lines on the return.
  ERPNext v16.51.1 accepts these returns without a link to an original invoice (tested
  manually, including the stock update).
- **VAT:** 20% for invoices to the United Kingdom and 0% (zero-rated exports) for all other
  countries, decided by each invoice's country rather than the customer's. All goods are
  standard-rated, and 20% applies throughout the history.   The templates are **United Kingdom Tax - MHG**
  and **Zero-Rated Export - MHG**.
- **Prices** are treated as excluding VAT. Revenue KPIs use net amounts; receivables use
  invoice totals including VAT.
- **Payment terms:** invoices are due 30 days after the invoice date.
- **Payments and refunds:** the Guest Customer pays on the day of the order. Other
  customers pay 10 to 50 days after the invoice, on a day derived from a hash of the
  invoice number, so every run produces the same dates. Returns are refunded on the same
  schedule; otherwise a return that is not linked to an original invoice would stay on
  the customer's account as a negative balance.


## Purchases and stock

- **Suppliers:** about 10 invented suppliers, each supplying one or two categories.
- **Restocking:** MHG buys each item's sales for the coming month plus a 20% safety buffer,
  at the item's cost. The first purchase is on the first day of the history (covering the
  rest of November 2023); after that, purchases happen on the first day of each month.
  Each purchase is a Purchase Invoice with stock updated, so it records both the
  supplier's bill and the goods arriving.
- **Returns** put goods back into stock through the return invoices.
- **Supplier payments** are out of scope.
- **Purchase VAT** is out of scope: purchase invoices carry no tax, like supplier payments.

## Loading

The master data is loaded with `uv run python -m bootstrap.load_master`, as the bootstrap
user. For each document type, the load lists what already exists in ERPNext and creates
only what is missing, comparing names ignoring case as ERPNext does. Running it again is
safe, and after an interruption it continues where it stopped. Existing documents are
never updated. Types are created in dependency order, because items and customers link
to groups and territories:

| Document type | Count |
|---|---|
| Item Group | 14 |
| Customer Group | 3 |
| Territory | 43 (one per invoice country) |
| Supplier Group | 1 |
| Supplier | 9 |
| Item | 4,750 |
| Customer | 5,878 |

Each stock item gets its cost as valuation rate, and its category's supplier and the
Stores - MHG warehouse as defaults. Suppliers are set per category in
`bootstrap/categories.toml`.

Invoices are loaded one month at a time with `uv run python -m bootstrap.load_invoices
YYYY-MM`, in three steps, each creating only what is missing:

1. **Purchases**, identified by their supplier invoice number (such as `2025-11 Northern
   Candle Co.`).
2. **Sales and returns**, identified by `custom_source_invoice`, created in date and
   time order, the order in which ERPNext values stock.
3. **Payments and refunds**, identified by their reference number (the source invoice
   number), built from the month's submitted invoices.

Cancelled documents do not count as existing. API requests do not get the defaults that
ERPNext's screens fill in, so every invoice sends its rates, warehouse, tax rows,
due date, and, on stock lines of returns, the item's cost as incoming rate. Temporary
database collisions with ERPNext's background jobs are retried with increasing waits.

November 2025 loaded 9 purchase invoices, 3,109 sales invoices and returns (81,051 lines),
and 3,109 payments and refunds.

Each loaded month is verified with `uv run python -m bootstrap.verify YYYY-MM`, which reads
ERPNext as the read-only pipeline user and compares it with the clean source, invoice by
invoice: total quantity, net total, VAT, grand total, customer, and payment status, plus
purchase quantity and value per supplier. Each line is rounded to pennies before lines
are added up, as ERPNext does, and differences of up to £0.01 per invoice are accepted.
The script exits with status 1 if any check fails.

November 2025 passed every check: 3,109 invoices, net sales of £1,410,899.40 and VAT of
£248,199.10, matching the source to the penny.

## Still to confirm

- The segment threshold, the category keywords, and the cost ratios, set when the
  cleaning code is written.
