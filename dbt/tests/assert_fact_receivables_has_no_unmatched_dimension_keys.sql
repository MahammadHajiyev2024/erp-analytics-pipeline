select *
from {{ ref('fact_receivables') }}
where due_date_key is null or customer_key is null
