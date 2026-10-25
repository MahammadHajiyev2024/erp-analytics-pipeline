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
- **Source keys:** simulated invoices are identified by keys such as
  `SIM-20251209-1-536365`: the simulated day, the copy (1, or 2 for an invoice placed
  twice), and the historical invoice it replays, in the same `custom_source_invoice` field
  as historical invoices. A replayed return keeps its C number at the end
  (`SIM-20251209-1-C536379`), so returns are recognized the same way as in the history.

## Payments

Payment dates follow the bootstrap's rule: the Guest Customer pays on the day of the
order, other customers 10 to 50 days after the invoice, and returns are refunded on the
same schedule. Unlike the bootstrap, a payment is recorded only when its day arrives, so
at any time recent invoices are partly unpaid, and some are overdue. Customers who never
pay (bad debts) are out of scope.

## New customers

When a replayed invoice was a customer's first-ever sale in the history, it is given to a
new customer instead, with the order's country and the original's segment, and an ID such
as `SIM-20251209-1-14911`, which ends with the customer it is modelled on.
The customer's other replayed orders stay with the original customer. New customers
therefore arrive at the historical rate and with the historical seasonality. Many new
customers place only one order, which understates how often new Wholesale customers
return; acquisition figures are realistic, detailed retention analysis is simplified.

## New products

On the first day of each simulated month, about 10 products that sell that month, chosen
by hash, are replaced by a successor: a new item with a code such as `85123A-N25` (the
launch year), a description ending in "2025 RANGE", the same category, supplier, and
typical price, and its own cost under the bootstrap's cost rule. From its launch month
on, all of the original's replayed sales and purchases go to the successor, and the
original is disabled in ERPNext. The choices depend only on the data and a hash, so every
month's successors are recalculated in each run rather than stored. A successor sells
exactly as its original did, which is realistic for category and revenue analysis but
simplified for the performance of new products.

## Changes to existing records

- **Segments:** on the first simulated day of each month, every customer's segment is
  recalculated with the bootstrap's rule (median net total of their submitted sales in
  ERPNext over the last 12 months, at least £150 for Wholesale), and changed segments are
  updated in ERPNext. Customers without orders in those 12 months keep their segment.
  These are the changes the SCD2 customer dimension keeps history for. The first review
  changes many customers at once, because the bootstrap's segments used each customer's
  whole history.
- **Cancellations:** about 0.5% of simulated sales invoices, chosen by hash and never
  returns or Guest Customer orders, are cancelled by the next day's run, before any
  payment. The pipeline must notice that a previously extracted invoice is no longer
  valid.
- **Discontinued products:** originals replaced by a successor are disabled (see above).

Changes to customer countries, product renames without a successor, and edits to invoice
lines are out of scope.

## Purchases

On the first simulated day of each month, MHG buys the whole month's simulated sales of
each stock item plus 20%, at cost, under the bootstrap's purchase rule. Their supplier
invoice numbers start with `SIM ` (such as `SIM 2025-12 Northern Candle Co.`), because
December 2025 also has a historical purchase per supplier.

## Timing

The simulator only simulates complete days, up to yesterday, and never creates documents
dated in the future. It finds the days still to simulate from ERPNext itself (the latest
simulated invoice), so the same command catches up after any gap: about ten months the
first time, then one day per daily run. Like the bootstrap, each step only creates what
is missing.

## Running and verifying

`uv run python -m simulator.run` is the daily command. It finds the latest simulated
invoice in ERPNext, simulates every day from the next one up to yesterday, and then
verifies the last 60 days, which covers every invoice whose payment status can have
changed (payments arrive up to 50 days after an invoice). Days without sales leave no
invoice behind and are simulated again by the next run, which creates nothing. The run
loads as the bootstrap user, verifies as the read-only pipeline user, and exits with
status 1 if the verification fails.

Because the simulator is deterministic, `uv run python -m simulator.verify FIRST LAST`
recalculates any range of simulated days and compares ERPNext with it: sales and returns
(to £0.01), exactly the chosen cancellations, which invoices are settled or still open on
the last day, each month's purchases per supplier, and successor products. Segment
reviews depend on ERPNext's own data at review time and are not verified.

## Test environment

The simulator is developed and tested against a separate ERPNext, started from the same
compose file under the project name `mhg-erpnext-test` on port 8081, and restored from the
master data backup. Test documents never reach the real books. The simulator commands
take `--test` to load `.env.test` on top of `.env`, which points them to port 8081.
