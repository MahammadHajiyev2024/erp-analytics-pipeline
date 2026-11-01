select purchase_invoice_id
from {{ ref('stg_purchase_invoice') }}
where docstatus = 2
