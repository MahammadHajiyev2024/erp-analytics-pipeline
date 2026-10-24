# Simulator rules

How Maple Home & Gift keeps trading after the historical data ends. The bootstrap (Phase 5)
loads the history up to 5 December 2025; the simulator (Phase 6) generates business
activity in ERPNext from 6 December 2025 onwards, one day at a time, so the pipeline has
new and changed data to extract every day (design decision 15).

## Generating a day

- **Replay:** each simulated day replays the invoices of the same weekday 52 weeks
  earlier, the latest historical day with the same weekday and season. Days more than a
  year past the history go back 104 weeks, then 156, always landing on a historical day.
  Which products are bought together, each customer's usual basket, the Christmas peak,
  and the closed days all come from the real data.
- **Variation:** every replayed invoice is varied deterministically, from a hash of the
  simulated date and the source invoice number, so simulating the same day twice produces
  the same documents. Some invoices are skipped and some are placed twice, and line
  quantities vary by up to 20%, so no simulated day is an exact copy.
- **Growth:** on balance, order count grows by 5% a year: more invoices are placed twice
  than skipped, by 5 percentage points for each year between the simulated day and its
  historical day. Prices stay as in the history, because item costs are fixed and higher
  prices would inflate margins.
- **Source keys:** simulated invoices are identified by keys such as `SIM-20251209-0001`
  (date and sequence), in the same `custom_source_invoice` field as historical invoices.

## Payments

Payment dates follow the bootstrap's rule: the Guest Customer pays on the day of the
order, other customers 10 to 50 days after the invoice, and returns are refunded on the
same schedule. Unlike the bootstrap, a payment is recorded only when its day arrives, so
at any time recent invoices are partly unpaid, and some are overdue. Customers who never
pay (bad debts) are out of scope.

## New customers

When a replayed invoice was a customer's first-ever order in the history, it is given to
a new customer instead, with the same country and segment and an ID such as `SIM-C00001`.
The customer's other replayed orders stay with the original customer. New customers
therefore arrive at the historical rate and with the historical seasonality. Many new
customers place only one order, which understates how often new Wholesale customers
return; acquisition figures are realistic, detailed retention analysis is simplified.

## New products

On the first day of each simulated month, about 10 products that sell that month, chosen
by hash, are replaced by a successor: a new item with a code such as `85123A-N26`, the
same category and supplier, and its own cost under the bootstrap's cost rule. From that
day on, all of the original's replayed sales go to the successor, and the original is
disabled in ERPNext. A successor sells exactly as its original did, which is realistic for
category and revenue analysis but simplified for the performance of new products.

## Changes to existing records

- **Segments:** on the first day of each simulated month, every customer's segment is
  recalculated with the bootstrap's rule (median order value of the last 12 months, at
  least £150 for Wholesale), and changed segments are updated in ERPNext. These are the
  changes the SCD2 customer dimension keeps history for.
- **Cancellations:** about 0.5% of simulated invoices, chosen by hash and never for the
  Guest Customer, are cancelled the day after they are created, before any payment. The
  pipeline must notice that a previously extracted invoice is no longer valid.
- **Discontinued products:** originals replaced by a successor are disabled (see above).

Changes to customer countries, product renames without a successor, and edits to invoice
lines are out of scope.

## Timing

The simulator only simulates complete days, up to yesterday, and never creates documents
dated in the future. It finds the days still to simulate from ERPNext itself (the latest
simulated invoice), so the same command catches up after any gap: about ten months the
first time, then one day per daily run. Like the bootstrap, each step only creates what
is missing.

## Test environment

The simulator is developed and tested against a separate ERPNext, started from the same
compose file under the project name `mhg-erpnext-test` on port 8081, and restored from the
master data backup. Test documents never reach the real books.
