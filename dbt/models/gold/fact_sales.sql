{{
    config(
        materialized='incremental',
        unique_key=['invoice_id', 'line_idx'],
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where not exists (
            select 1 from {{ ref('stg_sales_invoice') }} as s
            where s.sales_invoice_id = invoice_id and s.line_idx = line_idx
        )"
    )
}}

select
    d.date_key,
    c.customer_key,
    p.product_key,
    si.sales_invoice_id as invoice_id,
    si.line_idx,
    cast(si.is_return as boolean) as is_return,
    si.qty as quantity,
    si.net_amount as net_amount_gbp,
    si._ingested_at,
    si.net_amount * d.usd_per_gbp as net_amount_usd,
    si.qty * si.incoming_rate as cost_amount_gbp,
    si.qty * si.incoming_rate * d.usd_per_gbp as cost_amount_usd
from {{ ref('stg_sales_invoice') }} as si
left join {{ ref('dim_date') }} as d
    on si.posting_date = d.`date`
left join {{ ref('dim_customer') }} as c
    on
        si.customer_id = c.customer_id
        and si.posting_date >= cast(c.valid_from as date)
        and (si.posting_date < cast(c.valid_to as date) or c.valid_to is null)
left join {{ ref('dim_product') }} as p
    on si.item_id = p.product_id
{% if is_incremental() %}
    where si._ingested_at > (select max(t._ingested_at) from {{ this }} as t)
{% endif %}
