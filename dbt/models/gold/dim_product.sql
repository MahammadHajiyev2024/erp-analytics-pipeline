{{
    config(
        materialized='incremental',
        unique_key='product_key',
        incremental_strategy='merge'
    )
}}

select
    s.item_id as product_id,
    s.item_name as product_name,
    s.item_group as category,
    s._ingested_at,
    cast(s.is_stock_item as boolean) as is_stock_item,
    xxhash64(s.item_id) as product_key
from {{ ref('stg_item') }} as s
{% if is_incremental() %}
    where s._ingested_at > (select max(t._ingested_at) from {{ this }} as t)
{% endif %}
