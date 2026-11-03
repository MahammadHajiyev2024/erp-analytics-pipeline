select supplier_id
from {{ ref('stg_supplier') }}
where docstatus = 2
