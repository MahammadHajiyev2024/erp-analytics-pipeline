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

## 2. Managing Director

**Key questions (requirements.md):** How are revenue and profit trending, in GBP and USD? How
does performance compare with last year? Which countries and customer segments contribute most?

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | |
| Cards | `Net Revenue`, `Gross Profit`, `Gross Margin %`, `YoY Growth %` | Answers the trend + YoY questions directly |
| Line chart | `Net Revenue` by `dim_date` `Calendar` hierarchy | GBP/USD trend, drillable |
| Bar chart | `Net Revenue` by `dim_customer[country]` | |
| Bar chart | `Net Revenue` by `dim_customer[segment]` | |

---

## 3. Sales Manager

**Key questions (requirements.md):** Who are the top customers, and who is buying less? Which
products sell best, and which are bought together? How large are orders, and how often do
customers reorder?

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | |
| Table | `dim_customer[customer_name]`, `Net Revenue`, sorted descending | Top customers |
| Table | `dim_customer[customer_name]`, `Customer Revenue Change %`, sorted ascending | Customers buying less surface at the top (most negative change) |
| Bar chart | `Net Revenue` by `dim_product[product_name]`, Top N filter | Best-selling products |
| Matrix | `dim_product[product_id]` (rows) × `'Product B'[product_id]` (columns), value `Product Pair Frequency` | Bought-together pairs. **Apply a Basic (non-ranked) filter limiting both axes to ~5 products** — confirmed in Task 4 that an unfiltered full product grid times out |
| Cards | `Average Order Value`, `Repeat Purchase Rate` | Order size + reorder frequency |

**RLS demo note:** this is the page to screenshot under "View as Role" for Task 8's documentation
— switch to `Sales Manager - UK`, screenshot the top-customers table showing only UK rows, then
switch to `Sales Manager - France` and screenshot again. Remember RLS filters every page while a
role is active, not just this one (Task 5's note) — don't screenshot other pages while a role is
active unless that's the point.

---

## 4. Inventory Manager

**Key questions (requirements.md):** Which products are close to running out? Which aren't
selling and are tying up stock? How does demand change by season?

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | |
| Table | `dim_product[product_name]`, `Stock On Hand`, `Days of Stock Cover`, sorted ascending by `Days of Stock Cover` | Products closest to running out surface first. A known zero-sales product will show blank — expected (Task 4), not an error |
| Table | `dim_product[product_name]`, `Slow-Moving Stock Value`, `Stock Value On Hand` | Which products tie up stock with no sales in 90 days |
| Column chart | `Seasonal Index` by `dim_date` `Calendar` hierarchy (Month level) | Demand by season — November should read above 1.0 (Task 4 finding) |

---

## 5. Finance Manager

**Key questions (requirements.md):** What is the gross margin by category? How much do returns
cost? How much do customers owe, and how much is overdue?

| Visual | Fields | Notes |
|---|---|---|
| Currency slicer | `Currency[Currency]` | |
| Bar chart | `Gross Margin %` by `dim_product[category]` | Margin by category |
| Card | `Return Rate %` | Cost of returns, as a rate |
| Card | `Gross Profit` | For context next to margin |
| Table | `dim_customer[customer_name]`, `Accounts Receivable`, `Overdue %` | Amounts owed and overdue, per customer |

---

## Step 2 self-check

**Every stakeholder key question maps to at least one visual:**

| Stakeholder | Key question | Page / visual |
|---|---|---|
| Managing Director | Revenue/profit trending, GBP/USD | Managing Director — cards + line chart |
| Managing Director | vs. last year | Managing Director — `YoY Growth %` card |
| Managing Director | Countries/segments contributing most | Managing Director — bar charts |
| Sales Manager | Top customers / buying less | Sales Manager — top-customers table, `Customer Revenue Change %` table |
| Sales Manager | Best-selling products / bought together | Sales Manager — bar chart, `Product Pair Frequency` matrix |
| Sales Manager | Order size / reorder frequency | Sales Manager — `Average Order Value`, `Repeat Purchase Rate` cards |
| Inventory Manager | Close to running out | Inventory Manager — `Days of Stock Cover` table |
| Inventory Manager | Not selling / tying up stock | Inventory Manager — `Slow-Moving Stock Value` table |
| Inventory Manager | Demand by season | Inventory Manager — `Seasonal Index` chart |
| Finance Manager | Gross margin by category | Finance Manager — bar chart |
| Finance Manager | Cost of returns | Finance Manager — `Return Rate %` card |
| Finance Manager | Owed / overdue | Finance Manager — `Accounts Receivable` / `Overdue %` table |

**Every one of the 14 KPIs from `requirements.md` appears on at least one page:**

| KPI (requirements.md) | Measure(s) | Page(s) |
|---|---|---|
| Net revenue / Net revenue (USD) | `Net Revenue` | Overview, Managing Director, Sales Manager |
| Gross profit | `Gross Profit` | Overview, Finance Manager |
| Gross margin % | `Gross Margin %` | Overview, Finance Manager |
| Year-over-year growth % | `YoY Growth %` | Overview, Managing Director |
| Customer revenue change % | `Customer Revenue Change %` | Sales Manager |
| Product pair frequency | `Product Pair Frequency` | Sales Manager |
| Average order value | `Average Order Value` | Sales Manager |
| Repeat purchase rate | `Repeat Purchase Rate` | Sales Manager |
| Days of stock cover | `Days of Stock Cover` | Inventory Manager |
| Slow-moving stock value | `Slow-Moving Stock Value` | Inventory Manager |
| Seasonal index | `Seasonal Index` | Inventory Manager |
| Return rate % | `Return Rate %` | Finance Manager |
| Accounts receivable and overdue % | `Accounts Receivable`, `Overdue %` | Overview, Finance Manager |

(`Stock On Hand` and `Stock Value On Hand` are internal helper measures feeding `Days of Stock
Cover` and `Slow-Moving Stock Value` respectively — not separate KPI rows in `requirements.md`,
but shown directly in the Inventory Manager table since they're self-explanatory alongside the
measures they support.)
