select *
from {{ ref('fact_stock_movements') }}
where date_key is null or product_key is null
