{{
    config(
        materialized='incremental',
        unique_key='supplier_key',
        incremental_strategy='merge'
    )
}}

select
    s.supplier_id,
    s.supplier_name,
    s._ingested_at,
    xxhash64(s.supplier_id) as supplier_key
from {{ ref('stg_supplier') }} as s
{% if is_incremental() %}
    where s._ingested_at > (select max(t._ingested_at) from {{ this }} as t)
{% endif %}
