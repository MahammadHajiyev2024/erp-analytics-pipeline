{{
    config(
        materialized='incremental',
        unique_key='supplier_id',
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where docstatus = 2"
    )
}}

with ranked as (

    select
        b.name as supplier_id,
        b.raw:supplier_name::string as supplier_name,
        b.raw:supplier_group::string as supplier_group,
        b.raw:supplier_type::string as supplier_type,
        b.raw:country::string as country,
        b.modified,
        b.docstatus,
        b._ingested_at,
        row_number() over (
            partition by b.name
            order by b.modified desc, b._ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_supplier') }} as b
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

)

select
    supplier_id,
    supplier_name,
    supplier_group,
    supplier_type,
    country,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
