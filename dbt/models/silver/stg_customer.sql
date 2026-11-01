{{
    config(
        materialized='incremental',
        unique_key='customer_id',
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where docstatus = 2"
    )
}}

with ranked as (

    select
        b.name as customer_id,
        b.raw:customer_name::string as customer_name,
        b.raw:territory::string as territory,
        b.raw:customer_group::string as customer_group,
        b.modified,
        b.docstatus,
        b._ingested_at,
        row_number() over (
            partition by b.name
            order by b.modified desc, b._ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_customer') }} as b
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

)

select
    customer_id,
    customer_name,
    territory,
    customer_group,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
