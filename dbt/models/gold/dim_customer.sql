{{
    config(
        materialized='table'
    )
}}

with deduped as (

    select
        b.name as customer_id,
        b.raw:customer_name::string as customer_name,
        b.raw:territory::string as territory,
        b.raw:customer_group::string as customer_group,
        b.modified,
        row_number() over (
            partition by b.name, b.modified
            order by b._ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_customer') }} as b
    where b.docstatus is null or b.docstatus != 2

),

distinct_versions as (

    select
        customer_id,
        customer_name,
        territory,
        customer_group,
        modified
    from deduped
    where row_num = 1

),

change_flagged as (

    select
        *,
        case
            when
                lag(territory) over (
                    partition by customer_id order by modified
                ) is distinct from territory
                or lag(customer_group) over (
                    partition by customer_id order by modified
                ) is distinct from customer_group
                then 1
            else 0
        end as is_new_version
    from distinct_versions

),

numbered as (

    select
        *,
        sum(is_new_version) over (
            partition by customer_id
            order by modified
            rows between unbounded preceding and current row
        ) as version_number
    from change_flagged

),

grouped as (

    select
        customer_id,
        version_number,
        min(customer_name) as customer_name,
        min(territory) as territory,
        min(customer_group) as customer_group,
        min(modified) as valid_from
    from numbered
    group by customer_id, version_number

),

versions as (

    -- The first version's real valid_from is just when bronze first saw this
    -- customer, not when that state began -- it must cover every historical
    -- transaction that predates bronze, so it opens at a sentinel instead.
    -- Later versions keep their real valid_from: those are genuine changes.
    select
        customer_id,
        customer_name,
        territory,
        customer_group,
        case
            when
                row_number() over (
                    partition by customer_id order by valid_from
                ) = 1
                then '1900-01-01 00:00:00.000000'
            else valid_from
        end as valid_from,
        lead(valid_from) over (
            partition by customer_id order by valid_from
        ) as valid_to
    from grouped

)

select
    customer_id,
    customer_name,
    territory as country,
    customer_group as segment,
    valid_from,
    valid_to,
    valid_to is null as is_current,
    xxhash64(customer_id, valid_from) as customer_key
from versions
