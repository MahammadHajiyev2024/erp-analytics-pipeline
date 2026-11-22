# Report Pages

Visual spec for the 5 report pages Task 7 builds in Power BI Desktop. Each page maps directly to
one row of `docs/requirements.md`'s stakeholder table — no invented grouping, no chart that
doesn't trace back to a defined KPI or key question (the spec's anti-goal).

Every page that shows a monetary measure includes the `Currency[Currency]` slicer, since every
monetary measure in this model toggles GBP/USD via that disconnected table (not a per-KPI
decision). Non-monetary measures (`Gross Margin %`, `Return Rate %`, `Overdue %`, `YoY Growth %`,
`Customer Revenue Change %`, `Repeat Purchase Rate`, `Days of Stock Cover`, `Seasonal Index`,
`Product Pair Frequency`) are ratios/counts and aren't affected by the toggle, but the slicer
still needs to be on the page if any other visual there is monetary.

---

## 1. Overview

**Purpose:** company-wide landing page — the first thing a portfolio visitor sees.

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | Top of page |
| Cards | `Net Revenue`, `Gross Profit`, `Gross Margin %`, `YoY Growth %`, `Accounts Receivable`, `Overdue %` | Headline numbers across all four fact areas (sales, profit, receivables) |
| Line chart | `Net Revenue` by `dim_date` `Calendar` hierarchy (Year → Quarter → Month → Day) | Drillable trend; the hierarchy built in Task 4 |
| Bar chart | `Net Revenue` by `dim_customer[country]` | Which countries contribute most |
| Bar chart | `Net Revenue` by `dim_customer[segment]` | Which segments contribute most |

---

## 2. Management

**Key questions (requirements.md):** How are revenue and profit trending, in GBP and USD? How
does performance compare with last year? Which countries and customer segments contribute most?

**Architecture:** same layout as Overview/Sales — a 6-card KPI strip, a line chart + map side by
side, a donut + bar chart side by side, plus the same hidden filter pane (now page-scoped, see
the Sales section's bookmark note) and currency toggle.

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | |
| Cards | `Net Revenue`, `Gross Profit`, `Gross Margin %`, `YoY Growth %`, `Customer Revenue Change %`, `Total Active Customers` | Profit/growth-focused, deliberately not identical to Overview's card set |
| Line chart | `Net Revenue` and `Gross Profit` together by `dim_date` `Calendar` hierarchy | Two-measure trend (legend on) — Overview only shows Net Revenue alone |
| Map | `Net Revenue` by `dim_customer[country]` (size), `Customer Revenue Change %` (tooltip) | Geography still matters for an executive view; tooltip differs from Overview's |
| Donut | `Gross Profit` by `dim_customer[segment]` | Profit mix by segment, not just revenue mix — differs from Overview's revenue-by-segment donut |
| Bar chart | `Net Revenue` by `dim_customer[country]`, Top 5 filter | Which countries contribute most |

---

## 3. Sales

> Superseded the original tables/matrix design below. Customers in the UCI Online Retail II
> dataset are anonymized IDs with no real names, so a "top customers" table or chart isn't
> readable — this page instead answers sales questions in volume/behavior terms (orders, units,
> order size, reorder rate) rather than revenue/geography, which Overview already covers.

**Architecture:** same layout as Overview — a 6-card KPI strip, a line chart + bar chart side by
side, a donut + bar chart side by side, plus the same hidden filter pane and currency slicer.

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | Affects only `Average Order Value` on this page |
| Cards | `Total Orders`, `Average Order Value`, `Repeat Purchase Rate`, `Return Rate %`, `Total Active Customers`, `Total Units Sold` | No Net Revenue/Gross Profit/Margin here — those are Overview's cards |
| Line chart | `Total Units Sold` by `dim_date` `Calendar` hierarchy | Volume trend, drillable, mirrors Overview's revenue line |
| Bar chart | `Dynamic Order Volume` (`fact_receivables`) by `'Order Tiers'[Tier Name]` | "Orders by Amount Spent" — distribution of order sizes, not just the AOV average. Reuses the `Order Tiers`/`Dynamic Order Volume` measure built for the Finance page, so it's currency-aware: the £/$ thresholds themselves shift with the Currency toggle (a subtitle calls this out, since the tier labels — "Under 100", "100 - 500", etc. — don't carry a currency sign). **Known limitation:** `fact_receivables` has no relationship to `dim_product`, so this visual doesn't respond to the category slicer in the filter pane (it does respond to country/segment/Year) |
| Donut | `Total Units Sold` by `dim_product[category]` | Composition by volume instead of Overview's composition by revenue |
| Bar chart | `Total Units Sold` by `dim_product[product_name]`, Top 10 filter | Best-selling products — uses real product names, unlike customers |

**Dropped from the original design:** top-customers table, customer-revenue-change table (no
readable customer names), and the `Product Pair Frequency` matrix (kept as a measure for later
use, but not placed on this page to keep it in the Overview-style card/chart layout rather than
tables/matrices).

---

## 4. Inventory

**Key questions (requirements.md):** Which products are close to running out? Which aren't
selling and are tying up stock? How does demand change by season?

**Architecture:** same KPI-strip/filter-pane/currency-toggle shell as the other pages, but the
top-right slot is a table rather than a chart — with ~hundreds of products, a table reads more
precisely than a cramped bar chart would. **Known limitation:** `fact_stock_movements` has no
relationship to `dim_customer`, so this page's visuals don't respond to the country/segment
slicers in the filter pane (only category/Year do).

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | Affects `Stock Value On Hand` and `Slow-Moving Stock Value` only |
| Cards | `Stock Value On Hand`, `Stock On Hand`, `Avg Days of Stock Cover`, `Slow-Moving Stock Value`, `Total Units Sold`, `Seasonal Index` | `Avg Days of Stock Cover` is new: `AVERAGEX` over products, blanks (zero-sales products) excluded automatically |
| Line chart | `Seasonal Index` by `dim_date` `Calendar` hierarchy | Demand trend over time, same slot as other pages' line chart |
| Table | `dim_product[product_name]`, `Days of Stock Cover`, ascending, Top 15 | Products closest to running out surface first. A known zero-sales product will show blank — expected, not an error |
| Donut | `Stock Value On Hand` by `dim_product[category]` | Which categories tie up the most inventory value |
| Bar chart | `Slow-Moving Stock Value` by `dim_product[product_name]`, Top 10 filter | Which specific products are the worst dead-stock offenders |

---

## 5. Finance Report

**Key questions (requirements.md):** What is the gross margin by category? How much do returns
cost? How much do customers owe, and how much is overdue?

**Architecture:** same KPI-strip/filter-pane/currency-toggle shell as the other pages.

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | |
| Cards | `Gross Profit`, `Gross Margin %`, `Return Rate %`, `Accounts Receivable`, `Overdue %`, `Net Revenue` | `Accounts Receivable`'s format string was fixed here — it used to hard-code a `$` sign regardless of the currency toggle even though the underlying value switched GBP/USD |
| Line chart | `Gross Margin %` by `dim_date` `Calendar` hierarchy | Profitability trend — a new angle not shown on any other page |
| Map | `Accounts Receivable` by `dim_customer[country]` (size), `Overdue %` (tooltip) | Collections risk concentration by region |
| Donut | `Gross Profit` by `dim_product[category]` | Which categories are most profitable, not just which sell the most |
| Bar chart | `Accounts Receivable by Tier` (new measure) by `'Order Tiers'[Tier Name]` | How much is owed, broken down by invoice size — complements Sales' order-count-by-tier chart with a receivables-value view. Currency-aware like `Dynamic Order Volume` |

**Dropped from the original design:** a per-customer AR/overdue table — same anonymized-ID
problem as Sales' top-customers table, so it wasn't readable.

---

## Step 2 self-check

**Every stakeholder key question maps to at least one visual:**

| Stakeholder | Key question | Page / visual |
|---|---|---|
| Management | Revenue/profit trending, GBP/USD | Management — cards + line chart |
| Management | vs. last year | Management — `YoY Growth %` card |
| Management | Countries/segments contributing most | Management — map + bar chart, donut |
| Sales | Order volume and size | Sales — `Total Orders` card, `Order Size Tier` bar chart |
| Sales | Best-selling products | Sales — Top 10 products bar chart |
| Sales | Reorder frequency / returns | Sales — `Repeat Purchase Rate`, `Return Rate %` cards |
| Inventory | Close to running out | Inventory — `Days of Stock Cover` table |
| Inventory | Not selling / tying up stock | Inventory — `Slow-Moving Stock Value` bar chart, `Stock Value On Hand` donut |
| Inventory | Demand by season | Inventory — `Seasonal Index` card + line chart |
| Finance Report | Gross margin by category | Finance Report — `Gross Margin %` line chart, `Gross Profit` donut |
| Finance Report | Cost of returns | Finance Report — `Return Rate %` card |
| Finance Report | Owed / overdue | Finance Report — `Accounts Receivable` card + map, `Accounts Receivable by Tier` bar chart |

**Every one of the 14 KPIs from `requirements.md` appears on at least one page:**

| KPI (requirements.md) | Measure(s) | Page(s) |
|---|---|---|
| Net revenue / Net revenue (USD) | `Net Revenue` | Overview, Management, Finance Report |
| Gross profit | `Gross Profit` | Overview, Management, Finance Report |
| Gross margin % | `Gross Margin %` | Overview, Finance Report |
| Year-over-year growth % | `YoY Growth %` | Overview, Management |
| Customer revenue change % | `Customer Revenue Change %` | Management |
| Product pair frequency | `Product Pair Frequency` | None currently (measure retained; dropped from Sales to keep the card/chart layout) |
| Average order value | `Average Order Value` | Sales |
| Repeat purchase rate | `Repeat Purchase Rate` | Sales |
| Days of stock cover | `Days of Stock Cover` | Inventory |
| Slow-moving stock value | `Slow-Moving Stock Value` | Inventory |
| Seasonal index | `Seasonal Index` | Inventory |
| Return rate % | `Return Rate %` | Finance Report |
| Accounts receivable and overdue % | `Accounts Receivable`, `Overdue %` | Overview, Finance Report |

(`Stock On Hand` and `Stock Value On Hand` are internal helper measures feeding `Avg Days of
Stock Cover`/`Days of Stock Cover` and `Slow-Moving Stock Value` respectively — not separate KPI
rows in `requirements.md`, but shown directly as Inventory cards/visuals since they're
self-explanatory alongside the measures they support. `Accounts Receivable by Tier` similarly
extends `Accounts Receivable` rather than being a distinct `requirements.md` KPI.)

## Formatting convention

Every KPI measure across the model displays with exactly one decimal place — currency
(`#,0.0` / `$#,0.0` / `£#,0.0`), percentages (`0.0%;-0.0%;0.0%`), and plain counts/indices
(`#,0.0` / `0.0`) alike. This was standardized across `fact_sales`, `fact_receivables`, and
`fact_stock_movements` in this pass; several measures previously had 0 decimals or no explicit
format string at all.
