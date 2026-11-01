-- ADR 18: fact_sales.cost_amount_gbp will come from Sales Invoice Item's own
-- qty x incoming_rate; this checks that figure against the Stock Ledger
-- Entry it produced, joined on voucher_detail_no = the invoice line's own
-- child-row id (stg_sales_invoice.line_id). actual_qty is negative on an
-- outgoing sale and stock_value_difference moves with it, so a correct line
-- sums to (approximately) zero rather than matching directly.
select
    si.sales_invoice_id,
    si.line_id
from {{ ref('stg_sales_invoice') }} as si
inner join {{ ref('stg_stock_ledger_entry') }} as sle
    on si.line_id = sle.voucher_detail_no
where
    si.incoming_rate is not null
    and abs(si.qty * si.incoming_rate + sle.stock_value_difference) > 0.01
