select f.*
from {{ ref('fact_stock_movements') }} as f
where not exists (
    select 1 from {{ ref('stg_stock_ledger_entry') }} as s
    where s.entry_id = f.entry_id
)
