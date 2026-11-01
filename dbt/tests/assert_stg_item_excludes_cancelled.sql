select item_id
from {{ ref('stg_item') }}
where docstatus = 2
