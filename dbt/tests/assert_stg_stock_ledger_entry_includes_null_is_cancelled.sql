with ranked as (

    select
        name,
        raw:is_cancelled::int as is_cancelled,
        row_number() over (
            partition by name
            order by modified desc, _ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_stock_ledger_entry') }}

)

select count(*) as expected_count
from ranked
where row_num = 1 and (is_cancelled is null or is_cancelled != 1)
having
    expected_count
    != (select count(*) from {{ ref('stg_stock_ledger_entry') }})
