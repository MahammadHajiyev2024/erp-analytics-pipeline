# Requirements

Business requirements for the Maple Home & Gift analytics platform: who the dashboards serve,
what they need to know, how each answer is measured, and the project's scope.

## Stakeholders and key questions

| Stakeholder | Key questions |
|---|---|
| **Managing Director** | How are revenue and profit trending, in GBP and USD? How does performance compare with last year? Which countries and customer segments contribute most? |
| **Sales Manager** | Who are the top customers, and who is buying less? Which products sell best, and which are bought together? How large are orders, and how often do customers reorder? |
| **Inventory Manager** | Which products are close to running out? Which aren't selling and are tying up stock? How does demand change by season? |
| **Finance Manager** | What is the gross margin by category? How much do returns cost? How much do customers owe, and how much is overdue? |

## KPIs

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

## Scope and constraints

| Area | Decision |
|---|---|
| Data freshness | Daily batch updates |
| History | November 2011 first; extended to the full dataset (December 2009 to December 2011) once the pipeline works |
| Currency | Books in GBP; reporting in GBP and USD |
| Access | Sales views can be restricted by territory (row-level security) |
| Infrastructure | Runs on a 16 GB laptop with free services (Databricks Free Edition, Power BI Desktop) |

**Out of scope:** real-time data, manufacturing, HR and payroll, forecasting and machine learning,
full VAT and international tax compliance, and multiple companies or warehouses.

## Data assessment

Each question was checked against the available data before the KPIs were defined.

| Verdict | Questions |
|---|---|
| Answerable from real data | Best-selling products and product pairs; average order size; cost of returns |
| Answerable with assumptions | Revenue and profit trends; gross margin by category; customer segments |
| Answerable with simulated data | Customers buying less; stock running low; slow-moving stock; amounts owed and overdue |
| Requires the full history | Year-over-year comparison; seasonal demand; reorder frequency |

The full exploration is in [the exploration notebook](../notebooks/01_explore_online_retail.ipynb).
