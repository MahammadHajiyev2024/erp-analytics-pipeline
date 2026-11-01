{{
    config(
        materialized='incremental',
        unique_key=['purchase_invoice_id', 'line_idx'],
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where docstatus = 2"
    )
}}

with exploded as (

    select
        b.name as purchase_invoice_id,
        exploded_item.line_idx,
        b.raw:supplier::string as supplier_id,
        b.raw:posting_date::date as posting_date,
        exploded_item.item:item_code::string as item_id,
        exploded_item.item:qty::decimal(18, 4) as qty,
        exploded_item.item:net_amount::decimal(18, 2) as net_amount,
        b.modified,
        b.docstatus,
        b._ingested_at
    from {{ source('bronze', 'erpnext_purchase_invoice') }} as b
        lateral view posexplode(b.raw:items::array<variant>)
        exploded_item as line_idx, item
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

),

ranked as (

    select
        *,
        row_number() over (
            partition by purchase_invoice_id, line_idx
            order by modified desc, _ingested_at desc
        ) as row_num
    from exploded

)

select
    purchase_invoice_id,
    line_idx,
    supplier_id,
    posting_date,
    item_id,
    qty,
    net_amount,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
