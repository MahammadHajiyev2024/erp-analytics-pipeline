{{
    config(
        materialized='table'
    )
}}

with bounds as (

    select
        least(
            (select min(posting_date) from {{ ref('stg_sales_invoice') }}),
            (select min(posting_date) from {{ ref('stg_purchase_invoice') }}),
            (select min(posting_date) from {{ ref('stg_stock_ledger_entry') }}),
            (select min(observation_date) from {{ ref('stg_exchange_rate') }})
        ) as start_date,
        greatest(
            (select max(due_date) from {{ ref('stg_sales_invoice') }}),
            (select max(posting_date) from {{ ref('stg_purchase_invoice') }}),
            (select max(posting_date) from {{ ref('stg_stock_ledger_entry') }}),
            (select max(observation_date) from {{ ref('stg_exchange_rate') }})
        ) as end_date

),

calendar as (

    select `date`
    from bounds
        lateral view explode(
            sequence(start_date, end_date, interval 1 day)
        ) as `date`

),

with_rate as (

    select
        c.`date`,
        last_value(e.usd_per_gbp) ignore nulls over (
            order by c.`date`
            rows between unbounded preceding and current row
        ) as usd_per_gbp
    from calendar as c
    left join {{ ref('stg_exchange_rate') }} as e
        on c.`date` = e.observation_date

)

select
    `date`,
    usd_per_gbp,
    cast(date_format(`date`, 'yyyyMMdd') as int) as date_key,
    month(`date`) as `month`,
    date_format(`date`, 'MMM') as month_name,
    quarter(`date`) as `quarter`,
    concat('Qtr ', cast(quarter(`date`) as string)) as quarter_name,
    year(`date`) as `year`,
    dayofweek(`date`) in (1, 7) as is_weekend
from with_rate
