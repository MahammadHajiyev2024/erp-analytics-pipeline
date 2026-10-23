from datetime import date

from bootstrap.load_invoices import chronological, month_filters, purchase_date


def test_purchase_date_is_first_of_month_or_first_day_of_history():
    history_start = date(2023, 11, 28)

    assert purchase_date(date(2025, 11, 1), history_start) == date(2025, 11, 1)
    assert purchase_date(date(2023, 11, 1), history_start) == date(2023, 11, 28)


def test_chronological_orders_by_posting_date_and_time():
    def doc(source: str, day: str, time: str) -> dict:
        return {"custom_source_invoice": source, "posting_date": day, "posting_time": time}

    docs = [
        doc("C574000", "2025-11-03", "09:00:00"),
        doc("574200", "2025-11-20", "10:00:00"),
        doc("574100", "2025-11-03", "08:00:00"),
    ]

    keys = [doc["custom_source_invoice"] for doc in chronological(docs)]

    assert keys == ["574100", "C574000", "574200"]


def test_month_filters_cover_the_whole_month():
    filters = month_filters(date(2025, 11, 1))

    assert ["docstatus", "=", 1] in filters
    assert ["posting_date", "between", ["2025-11-01", "2025-11-30"]] in filters
