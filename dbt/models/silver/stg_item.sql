{{
    config(
        materialized='incremental',
        unique_key='item_id',
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where docstatus = 2"
    )
}}

with ranked as (

    select
        b.name as item_id,
        b.raw:item_name::string as item_name,
        b.raw:item_group::string as item_group,
        b.raw:is_stock_item::int as is_stock_item,
        b.modified,
        b.docstatus,
        b._ingested_at,
        row_number() over (
            partition by b.name
            order by b.modified desc, b._ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_item') }} as b
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

)

select
    item_id,
    item_name,
    item_group,
    is_stock_item,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
