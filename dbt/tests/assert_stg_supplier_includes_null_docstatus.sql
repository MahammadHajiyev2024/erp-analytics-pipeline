with ranked as (

    select
        name,
        docstatus,
        row_number() over (
            partition by name
            order by modified desc, _ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_supplier') }}

)

select count(*) as expected_count
from ranked
where row_num = 1 and (docstatus is null or docstatus != 2)
having expected_count != (select count(*) from {{ ref('stg_supplier') }})
