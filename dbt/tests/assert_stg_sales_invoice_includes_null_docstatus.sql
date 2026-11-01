with exploded as (

    select
        b.name,
        exploded_item.line_idx,
        b.modified,
        b.docstatus,
        b._ingested_at
    from {{ source('bronze', 'erpnext_sales_invoice') }} as b
        lateral view posexplode(b.raw:items::array<variant>)
        exploded_item as line_idx, item

),

ranked as (

    select
        *,
        row_number() over (
            partition by name, line_idx
            order by modified desc, _ingested_at desc
        ) as row_num
    from exploded

)

select count(*) as expected_count
from ranked
where row_num = 1 and (docstatus is null or docstatus != 2)
having expected_count != (select count(*) from {{ ref('stg_sales_invoice') }})
