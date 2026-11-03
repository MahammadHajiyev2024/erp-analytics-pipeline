select *
from {{ ref('fact_sales') }}
where date_key is null or customer_key is null or product_key is null
