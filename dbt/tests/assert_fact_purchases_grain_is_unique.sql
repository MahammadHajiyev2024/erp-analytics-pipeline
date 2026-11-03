select invoice_id, line_idx, count(*) as row_count
from {{ ref('fact_purchases') }}
group by invoice_id, line_idx
having count(*) > 1
