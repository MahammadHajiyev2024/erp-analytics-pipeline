{{
    config(
        materialized='incremental',
        unique_key='observation_date',
        incremental_strategy='merge'
    )
}}

with source_cast as (

    -- raw:value::string is extracted here, once, into a plain column. Reusing
    -- the VARIANT path accessor a second time inside the CASE expression
    -- below (once in the WHEN, once in the ELSE) made Databricks error on
    -- some rows with INVALID_VARIANT_CAST, even though each cast works fine
    -- on its own.
    select
        b.series_id,
        b.observation_date::date as observation_date,
        b.raw:value::string as value_text,
        b._ingested_at
    from {{ source('bronze', 'fred_exchange_rates') }} as b
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

),

ranked as (

    select
        series_id,
        observation_date,
        _ingested_at,
        case
            when value_text = '.' then null
            else value_text::decimal(18, 6)
        end as usd_per_gbp,
        row_number() over (
            partition by observation_date
            order by _ingested_at desc
        ) as row_num
    from source_cast

)

select
    observation_date,
    usd_per_gbp,
    series_id,
    _ingested_at
from ranked
where row_num = 1
