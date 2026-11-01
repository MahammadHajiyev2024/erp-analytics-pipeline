select sales_invoice_id
from {{ ref('stg_sales_invoice') }}
where docstatus = 2
