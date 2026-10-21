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

Stock codes are trimmed of surrounding spaces when the source is loaded.

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

- **Missing customer ID** (23% of rows): the order belongs to a single **Guest Customer**.
- **Segments:** a customer is **Wholesale** if their median order value is above a
  threshold, otherwise **Retail**. The threshold is chosen from the order value
  distribution when the cleaning code is written. The Guest Customer is always Retail.

## Products

- **Categories:** each product gets one category (an ERPNext Item Group) from keyword
  rules on its description. Rules are checked in a fixed order and the first match wins,
  so seasonal categories such as Christmas come first. Unmatched products go to
  **Other**, which should stay below about 10–15% of products. The keywords live in a
  file in the repository and are covered by unit tests.
- **Service items:** shipping codes (`POST`, `DOT`, `C2`) and discounts become non-stock
  service items named **Shipping** and **Discount**.
- **Costs:** each stock item has one fixed cost: its median selling price multiplied by
  its category's cost ratio, plus a small adjustment of up to about ±5 percentage points
  derived from the stock code. The adjustment is deterministic, so every run produces the
  same costs. Cost ratios aim at gross margins of roughly 40–50%. Shipping passes through
  at cost (no margin); discounts have no cost.

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

## Still to confirm

- The segment threshold, the category keywords, and the cost ratios, set when the
  cleaning code is written.
