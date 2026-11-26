# Report Pages

Visual spec for the 4 report pages Task 7 builds in Power BI Desktop. Each page maps directly to
one row of `docs/requirements.md`'s stakeholder table — no invented grouping, no chart that
doesn't trace back to a defined KPI or key question (the spec's anti-goal).

Every page that shows a monetary measure includes the `Currency[Currency]` slicer, since every
monetary measure in this model toggles GBP/USD via that disconnected table (not a per-KPI
decision). Non-monetary measures (`Gross Margin %`, `Return Rate %`, `Overdue %`, `YoY Growth %`,
`Customer Revenue Change %`, `Repeat Purchase Rate`, `Days of Stock Cover`, `Seasonal Index`,
`Product Pair Frequency`, `Days Sales Outstanding`) are ratios/counts and aren't affected by the
toggle (for `Days Sales Outstanding` the GBP/USD conversion cancels out in the division), but the
slicer still needs to be on the page if any other visual there is monetary.

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

## 2. Sales

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

## 3. Inventory

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

## 4. Finance Report

**Key questions (requirements.md):** What is the gross margin by category? How much do returns
cost? How much do customers owe, and how much is overdue?

**Architecture:** same KPI-strip/filter-pane/currency-toggle shell as the other pages.

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | |
| Cards | `Gross Profit`, `Gross Margin %`, `Days Sales Outstanding`, `Accounts Receivable`, `Overdue %`, `Net Revenue` | `Accounts Receivable`'s format string was fixed here — it used to hard-code a `$` sign regardless of the currency toggle even though the underlying value switched GBP/USD. `Return Rate %` was swapped out for `Days Sales Outstanding` — a finance page is the wrong home for a returns-frequency metric that already lives on Sales |
| Line chart | `Gross Margin %` by `dim_date` `Calendar` hierarchy | Profitability trend — a new angle not shown on any other page |
| Table | `dim_customer[country]`, `Accounts Receivable`, `Country Share of Total AR` (new measure), `Overdue %`, Top 10 filter | Replaced a bubble map, then a ranked bar: the source dataset is so UK-dominated that both a map and a bar collapse to "one giant value, rest invisible" — a length-comparison visual can't show anything once one country's AR this thoroughly dominates. A table sidesteps the skew entirely: it's a lookup task (exact figures per country), not a magnitude-comparison task. `Country Share of Total AR` shows each country's share of the *whole* receivables book (via `ALL(dim_customer[country])`), not just its slice of the Top 10 shown |
| Donut | `Gross Profit` by `dim_product[category]`, Top 5 filter | Originally all 11 categories (10 named + "Other"), which is past where a donut's color-and-label matching stays readable. Limiting to the Top 5 by Gross Profit fixes the legibility problem without abandoning the donut shape — also gives this page more visual variety against the two other table/bar visuals. Title says "Top 5" explicitly since the percent-of-total labels are relative to the Top 5's own sum, not the page-wide total |
| Bar chart | `Accounts Receivable by Tier` (new measure) by `'Order Tiers'[Tier Name]` | How much is owed, broken down by invoice size — complements Sales' order-count-by-tier chart with a receivables-value view. Currency-aware like `Dynamic Order Volume` |

**Dropped from the original design:** a per-customer AR/overdue table — same anonymized-ID
problem as Sales' top-customers table, so it wasn't readable.

---

## Step 2 self-check

**Every stakeholder key question maps to at least one visual:**

| Stakeholder | Key question | Page / visual |
|---|---|---|
| Sales | Order volume and size | Sales — `Total Orders` card, `Order Size Tier` bar chart |
| Sales | Best-selling products | Sales — Top 10 products bar chart |
| Sales | Reorder frequency / returns | Sales — `Repeat Purchase Rate`, `Return Rate %` cards |
| Inventory | Close to running out | Inventory — `Days of Stock Cover` table |
| Inventory | Not selling / tying up stock | Inventory — `Slow-Moving Stock Value` bar chart, `Stock Value On Hand` donut |
| Inventory | Demand by season | Inventory — `Seasonal Index` card + line chart |
| Finance Report | Gross margin by category | Finance Report — `Gross Margin %` line chart, `Gross Profit` donut (Top 5) |
| Finance Report | Cost of returns | Sales — `Return Rate %` card (not shown on Finance Report after this pass; it's a returns-frequency metric, not a currency cost, and fits Sales' theme better) |
| Finance Report | Owed / overdue | Finance Report — `Accounts Receivable` card + table, `Accounts Receivable by Tier` bar chart |

**Every one of the 14 KPIs from `requirements.md` appears on at least one page:**

| KPI (requirements.md) | Measure(s) | Page(s) |
|---|---|---|
| Net revenue / Net revenue (USD) | `Net Revenue` | Overview, Finance Report |
| Gross profit | `Gross Profit` | Overview, Finance Report |
| Gross margin % | `Gross Margin %` | Overview, Finance Report |
| Year-over-year growth % | `YoY Growth %` | Overview |
| Customer revenue change % | `Customer Revenue Change %` | None currently (measure retained; previously shown on Management, which was removed) |
| Product pair frequency | `Product Pair Frequency` | None currently (measure retained; dropped from Sales to keep the card/chart layout) |
| Average order value | `Average Order Value` | Sales |
| Repeat purchase rate | `Repeat Purchase Rate` | Sales |
| Days of stock cover | `Days of Stock Cover` | Inventory |
| Slow-moving stock value | `Slow-Moving Stock Value` | Inventory |
| Seasonal index | `Seasonal Index` | Inventory |
| Return rate % | `Return Rate %` | Sales |
| Accounts receivable and overdue % | `Accounts Receivable`, `Overdue %` | Overview, Finance Report |

(`Stock On Hand` and `Stock Value On Hand` are internal helper measures feeding `Avg Days of
Stock Cover`/`Days of Stock Cover` and `Slow-Moving Stock Value` respectively — not separate KPI
rows in `requirements.md`, but shown directly as Inventory cards/visuals since they're
self-explanatory alongside the measures they support. `Accounts Receivable by Tier` similarly
extends `Accounts Receivable` rather than being a distinct `requirements.md` KPI. `Days Sales
Outstanding` (`fact_receivables.tmdl`) is a later addition, also not one of the original 14 —
added during the Financial Report/Inventory visual-refinement pass to replace `Return Rate %` on
Finance Report's card row with a measure that actually fits a finance page's theme: average days
to collect revenue, built from `Accounts Receivable` ÷ `Net Revenue` × days in the selected
period, no dbt/gold changes needed. `Country Share of Total AR` (`fact_receivables.tmdl`) is
another later addition from the same pass — each country's share of the whole receivables book,
added as a 4th column on the AR-by-country table to use space the 3 original columns left empty.)

## Formatting convention

Every KPI measure across the model displays with exactly one decimal place — currency
(`#,0.0` / `$#,0.0` / `£#,0.0`), percentages (`0.0%;-0.0%;0.0%`), and plain counts/indices
(`#,0.0` / `0.0`) alike. This was standardized across `fact_sales`, `fact_receivables`, and
`fact_stock_movements` in this pass; several measures previously had 0 decimals or no explicit
format string at all.
