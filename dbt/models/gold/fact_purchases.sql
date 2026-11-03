{{
    config(
        materialized='incremental',
        unique_key=['invoice_id', 'line_idx'],
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where not exists (
            select 1 from {{ ref('stg_purchase_invoice') }} as s
            where s.purchase_invoice_id = invoice_id and s.line_idx = line_idx
        )"
    )
}}

select
    d.date_key,
    s.supplier_key,
    p.product_key,
    pi.purchase_invoice_id as invoice_id,
    pi.line_idx,
    pi.qty as quantity,
    pi.net_amount as amount_gbp,
    pi._ingested_at,
    pi.net_amount * d.usd_per_gbp as amount_usd
from {{ ref('stg_purchase_invoice') }} as pi
left join {{ ref('dim_date') }} as d
    on pi.posting_date = d.`date`
left join {{ ref('dim_supplier') }} as s
    on pi.supplier_id = s.supplier_id
left join {{ ref('dim_product') }} as p
    on pi.item_id = p.product_id
{% if is_incremental() %}
    where pi._ingested_at > (select max(t._ingested_at) from {{ this }} as t)
{% endif %}
