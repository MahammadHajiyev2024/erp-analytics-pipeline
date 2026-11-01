select customer_id
from {{ ref('stg_customer') }}
where docstatus = 2
