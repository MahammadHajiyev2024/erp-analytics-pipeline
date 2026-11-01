{#
    Stock Ledger Entry never carries docstatus = 2: every row observed in bronze is
    docstatus = 1, because an SLE inherits submission state from its source invoice
    rather than being submitted/cancelled itself. is_cancelled is the real flag,
    set when that source invoice is cancelled (see ADR 18).
#}
{{
    config(
        materialized='incremental',
        unique_key='entry_id',
        incremental_strategy='merge',
        post_hook="delete from {{ this }} where is_cancelled = 1"
    )
}}

with ranked as (

    select
        b.name as entry_id,
        b.raw:item_code::string as item_id,
        b.raw:posting_date::date as posting_date,
        b.raw:voucher_type::string as voucher_type,
        b.raw:voucher_no::string as voucher_no,
        b.raw:voucher_detail_no::string as voucher_detail_no,
        b.raw:actual_qty::decimal(18, 4) as actual_qty,
        b.raw:qty_after_transaction::decimal(18, 4) as qty_after_transaction,
        b.raw:warehouse::string as `warehouse`,
        b.raw:incoming_rate::decimal(18, 4) as incoming_rate,
        b.raw:stock_value_difference::decimal(18, 4) as stock_value_difference,
        b.raw:is_cancelled::int as is_cancelled,
        b.modified,
        b.docstatus,
        b._ingested_at,
        row_number() over (
            partition by b.name
            order by b.modified desc, b._ingested_at desc
        ) as row_num
    from {{ source('bronze', 'erpnext_stock_ledger_entry') }} as b
    {% if is_incremental() %}
        where
            b._ingested_at > (
                select max(t._ingested_at) from {{ this }} as t
            )
    {% endif %}

)

select
    entry_id,
    item_id,
    posting_date,
    voucher_type,
    voucher_no,
    voucher_detail_no,
    actual_qty,
    qty_after_transaction,
    `warehouse`,
    incoming_rate,
    stock_value_difference,
    is_cancelled,
    modified,
    docstatus,
    _ingested_at
from ranked
where row_num = 1
