select f.*
from {{ ref('fact_sales') }} as f
where not exists (
    select 1 from {{ ref('stg_sales_invoice') }} as s
    where s.sales_invoice_id = f.invoice_id and s.line_idx = f.line_idx
)
