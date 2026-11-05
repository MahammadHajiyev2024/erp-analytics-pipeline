{{
    config(
        materialized='table'
    )
}}

with headers as (

    select distinct
        sales_invoice_id,
        customer_id,
        posting_date,
        due_date,
        outstanding_amount,
        grand_total
    from {{ ref('stg_sales_invoice') }}

)

select
    d.date_key as due_date_key,
    c.customer_key,
    h.sales_invoice_id as invoice_id,
    h.grand_total as invoice_amount_gbp,
    h.outstanding_amount as outstanding_amount_gbp,
    h.grand_total * d.usd_per_gbp as invoice_amount_usd,
    h.outstanding_amount * d.usd_per_gbp as outstanding_amount_usd,
    h.due_date < current_date() and h.outstanding_amount > 0 as is_overdue
from headers as h
left join {{ ref('dim_date') }} as d
    on h.due_date = d.`date`
left join {{ ref('dim_customer') }} as c
    on
        h.customer_id = c.customer_id
        and h.posting_date >= cast(c.valid_from as date)
        and (h.posting_date < cast(c.valid_to as date) or c.valid_to is null)
