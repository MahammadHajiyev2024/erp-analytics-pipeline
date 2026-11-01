select entry_id
from {{ ref('stg_stock_ledger_entry') }}
where is_cancelled = 1
