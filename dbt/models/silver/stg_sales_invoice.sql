{{
    config(
        materialized='incremental',
        unique_key=['sales_invoice_id', 'line_idx'],
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where docstatus = 2"
    )
}}

with exploded as (

    select
        b.name as sales_invoice_id,
        exploded_item.line_idx,
        b.raw:customer::string as customer_id,
        b.raw:posting_date::date as posting_date,
        b.raw:due_date::date as due_date,
        b.raw:is_return::int as is_return,
        b.raw:outstanding_amount::decimal(18, 2) as outstanding_amount,
        b.raw:grand_total::decimal(18, 2) as grand_total,
        exploded_item.item:name::string as line_id,
        exploded_item.item:item_code::string as item_id,
        exploded_item.item:qty::decimal(18, 4) as qty,
        exploded_item.item:net_amount::decimal(18, 2) as net_amount,
        exploded_item.item:incoming_rate::decimal(18, 4) as incoming_rate,
        b.modified,
        b.docstatus,
        b._ingested_at
    from {{ source('bronze', 'erpnext_sales_invoice') }} as b
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
            partition by sales_invoice_id, line_idx
            order by modified desc, _ingested_at desc
        ) as row_num
    from exploded

)

select
    sales_invoice_id,
    line_idx,
    customer_id,
    posting_date,
    due_date,
    is_return,
    outstanding_amount,
    grand_total,
    line_id,
    item_id,
    qty,
    net_amount,
    incoming_rate,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
