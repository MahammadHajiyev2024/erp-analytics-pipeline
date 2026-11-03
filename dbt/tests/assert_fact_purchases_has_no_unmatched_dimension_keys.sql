select *
from {{ ref('fact_purchases') }}
where date_key is null or supplier_key is null or product_key is null
