select invoice_id, line_idx, count(*) as row_count
from {{ ref('fact_sales') }}
group by invoice_id, line_idx
having count(*) > 1
