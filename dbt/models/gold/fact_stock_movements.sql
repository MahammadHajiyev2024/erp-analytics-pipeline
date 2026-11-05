{{
    config(
        materialized='incremental',
        unique_key='entry_id',
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where not exists (
            select 1 from {{ ref('stg_stock_ledger_entry') }} as s
            where s.entry_id = entry_id
        )"
    )
}}

select
    d.date_key,
    p.product_key,
    sle.entry_id,
    sle.voucher_type,
    sle.actual_qty as quantity_change,
    sle.qty_after_transaction as balance_quantity,
    sle.stock_value_difference as value_change_gbp,
    sle._ingested_at,
    sle.stock_value_difference * d.usd_per_gbp as value_change_usd
from {{ ref('stg_stock_ledger_entry') }} as sle
left join {{ ref('dim_date') }} as d
    on sle.posting_date = d.`date`
left join {{ ref('dim_product') }} as p
    on sle.item_id = p.product_id
{% if is_incremental() %}
    where sle._ingested_at > (select max(t._ingested_at) from {{ this }} as t)
{% endif %}
