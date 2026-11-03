select f.*
from {{ ref('fact_purchases') }} as f
where not exists (
    select 1 from {{ ref('stg_purchase_invoice') }} as s
    where s.purchase_invoice_id = f.invoice_id and s.line_idx = f.line_idx
)
