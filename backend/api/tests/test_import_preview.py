from datetime import datetime
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from api.models import Expense, StockMovement


PREVIEW_URL = "/api/imports/preview"


def csv_file(name, *lines):
    return SimpleUploadedFile(
        name,
        ("\n".join(lines) + "\n").encode("utf-8"),
        content_type="text/csv",
    )


def upload(client, entity_type, upload_file):
    return client.post(
        PREVIEW_URL,
        {"entityType": entity_type, "file": upload_file},
        format="multipart",
    )


def xlsx_file(name, rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    for row in rows:
        worksheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return SimpleUploadedFile(
        name,
        stream.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )


def make_item(client, unit, name="Nitrogen"):
    response = client.post(
        "/api/inventory-items",
        {"name": name, "unitId": unit["id"], "reorderLevel": "2"},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def test_expenses_csv_preview_is_valid_and_read_only(client, cycle):
    cycle_data = cycle()
    before = Expense.objects.count()

    response = upload(
        client,
        "expenses",
        csv_file(
            "expenses.csv",
            "date,category,amount,supplier,notes,cycleId",
            (
                "2026-03-01,inputs,250.50,Agro Supply,Seed purchase,"
                f"{cycle_data['cycle']['id']}"
            ),
            "2026-03-02,labour,100,,,",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["entityType"] == "expenses"
    assert body["fileName"] == "expenses.csv"
    assert body["totalRows"] == 2
    assert body["counts"] == {
        "total": 2,
        "valid": 2,
        "invalid": 0,
        "duplicate": 0,
    }
    first = body["validRows"][0]
    assert first["row"] == 2
    assert first["date"] == "2026-03-01"
    assert first["category"] == "inputs"
    assert first["amount"] == 250.5
    assert first["supplier"] == "Agro Supply"
    assert first["notes"] == "Seed purchase"
    assert first["cycleId"] == cycle_data["cycle"]["id"]
    second = body["validRows"][1]
    assert second["supplier"] is None
    assert second["notes"] is None
    assert second["cycleId"] is None
    assert Expense.objects.count() == before


def test_inventory_movements_csv_preview_is_valid(client, setup):
    data = setup()
    item = make_item(client, data["unit"])
    before = StockMovement.objects.count()

    response = upload(
        client,
        "inventory_movements",
        csv_file(
            "movements.csv",
            "item,type,quantity,date,note",
            "Nitrogen,purchase,10,2026-03-02,Initial stock",
            "nitrogen,usage,3,2026-03-03,",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["entityType"] == "inventory_movements"
    assert body["counts"] == {
        "total": 2,
        "valid": 2,
        "invalid": 0,
        "duplicate": 0,
    }
    assert [row["type"] for row in body["validRows"]] == [
        "purchase",
        "usage",
    ]
    assert body["validRows"][0]["itemId"] == item["id"]
    assert body["validRows"][0]["item"] == "Nitrogen"
    assert body["validRows"][0]["quantity"] == 10
    assert body["validRows"][1]["date"] == "2026-03-03"
    assert body["validRows"][1]["note"] is None
    assert StockMovement.objects.count() == before


def test_expenses_csv_collects_all_row_errors(client):
    response = upload(
        client,
        "expenses",
        csv_file(
            "expenses.csv",
            "date,category,amount,supplier,notes,cycleId",
            "2026-03-01,inputs,10,,,",
            "not-a-date,inputs,10,,,",
            "2026-03-01,rent,10,,,",
            "2026-03-01,inputs,abc,,,",
            "2026-03-01,inputs,-1,,,",
            "2026-03-01,inputs,10,,,00000000-0000-0000-0000-000000000000",
            "2026-03-01,inputs,,,",
            "bad-date,rent,-5,,,",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["counts"] == {
        "total": 8,
        "valid": 1,
        "invalid": 7,
        "duplicate": 0,
    }
    errors = {row["row"]: row["errors"] for row in body["invalidRows"]}
    assert [error["field"] for error in errors[3]] == ["date"]
    assert [error["field"] for error in errors[4]] == ["category"]
    assert [error["field"] for error in errors[5]] == ["amount"]
    assert "number" in errors[5][0]["message"]
    assert [error["field"] for error in errors[6]] == ["amount"]
    assert "greater than zero" in errors[6][0]["message"]
    assert [error["field"] for error in errors[7]] == ["cycleId"]
    assert [error["field"] for error in errors[8]] == ["amount"]
    assert {error["field"] for error in errors[9]} == {
        "date",
        "category",
        "amount",
    }
    assert len(errors[9]) == 3


def test_inventory_movements_csv_collects_all_row_errors(client, setup):
    make_item(client, setup()["unit"])

    response = upload(
        client,
        "inventory_movements",
        csv_file(
            "movements.csv",
            "item,type,quantity,date,note",
            "Nitrogen,purchase,10,2026-03-02,",
            "Unknown,waste,0,not-a-date,",
            "Nitrogen,usage,abc,,",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["counts"] == {
        "total": 3,
        "valid": 1,
        "invalid": 2,
        "duplicate": 0,
    }
    first = body["invalidRows"][0]
    assert first["row"] == 3
    assert {error["field"] for error in first["errors"]} == {
        "item",
        "type",
        "quantity",
        "date",
    }
    assert "Unknown" in first["errors"][0]["message"]
    second = body["invalidRows"][1]
    assert {error["field"] for error in second["errors"]} == {
        "date",
        "quantity",
    }


def test_expenses_duplicates_are_flagged_in_file_and_against_db(client):
    existing = client.post(
        "/api/expenses",
        {
            "category": "inputs",
            "amount": "100",
            "date": "2026-03-05",
            "supplier": "Agro",
        },
        format="json",
    )
    assert existing.status_code == 201
    before = Expense.objects.count()

    response = upload(
        client,
        "expenses",
        csv_file(
            "expenses.csv",
            "date,category,amount,supplier",
            "2026-03-05,inputs,100.00,agro",
            "2026-03-06,labour,50,",
            "2026-03-06,labour,50.0000,",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["counts"] == {
        "total": 3,
        "valid": 1,
        "invalid": 0,
        "duplicate": 2,
    }
    assert [row["row"] for row in body["validRows"]] == [3]
    assert body["validRows"][0]["amount"] == 50
    duplicates = {row["row"]: row for row in body["duplicateRows"]}
    assert "existing" in duplicates[2]["reason"].lower()
    assert "row 3" in duplicates[4]["reason"]
    assert duplicates[2]["key"] == {
        "date": "2026-03-05",
        "category": "inputs",
        "amount": 100.0,
        "supplier": "agro",
    }
    assert Expense.objects.count() == before


def test_movement_duplicates_are_flagged_in_file_and_against_db(
    client, setup
):
    data = setup()
    item = make_item(client, data["unit"])
    existing = client.post(
        f"/api/inventory-items/{item['id']}/movements",
        {
            "itemId": item["id"],
            "type": "purchase",
            "quantity": "10",
            "date": "2026-03-02",
            "note": "Initial",
        },
        format="json",
    )
    assert existing.status_code == 201
    before = StockMovement.objects.count()

    response = upload(
        client,
        "inventory_movements",
        csv_file(
            "movements.csv",
            "item,type,quantity,date,note",
            "Nitrogen,purchase,10.0,2026-03-02,Initial",
            "Nitrogen,usage,3,2026-03-03,",
            "Nitrogen,usage,3.00,2026-03-03,",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["counts"] == {
        "total": 3,
        "valid": 1,
        "invalid": 0,
        "duplicate": 2,
    }
    assert [row["row"] for row in body["validRows"]] == [3]
    duplicates = {row["row"]: row for row in body["duplicateRows"]}
    assert "existing" in duplicates[2]["reason"].lower()
    assert "row 3" in duplicates[4]["reason"]
    assert duplicates[2]["key"]["itemId"] == item["id"]
    assert StockMovement.objects.count() == before


def test_csv_preview_handles_bom_and_quoted_newlines(client):
    bom = upload(
        client,
        "expenses",
        SimpleUploadedFile(
            "bom.csv",
            (
                b"\xef\xbb\xbfdate,category,amount\n"
                b"2026-03-01,inputs,10\n"
            ),
            content_type="text/csv",
        ),
    )
    assert bom.status_code == 200, bom.data
    assert bom.data["counts"]["valid"] == 1

    quoted = upload(
        client,
        "expenses",
        csv_file(
            "quoted.csv",
            "date,category,amount,notes",
            '2026-03-01,inputs,10,"first line\nsecond line"',
        ),
    )
    assert quoted.status_code == 200, quoted.data
    assert quoted.data["validRows"][0]["notes"] == (
        "first line\nsecond line"
    )


def test_empty_file_is_rejected(client):
    response = upload(
        client,
        "expenses",
        SimpleUploadedFile("empty.csv", b"", content_type="text/csv"),
    )
    assert response.status_code == 400
    assert response.data["field"] == "file"
    assert "empty" in response.data["detail"].lower()


def test_structural_header_errors_are_rejected(client):
    missing = upload(
        client,
        "expenses",
        csv_file("missing.csv", "date,amount", "2026-03-01,10"),
    )
    assert missing.status_code == 400
    assert missing.data["field"] == "file"
    assert "Missing required header" in missing.data["detail"]
    assert "category" in missing.data["detail"]

    extra = upload(
        client,
        "expenses",
        csv_file(
            "extra.csv",
            "date,category,amount,bogus",
            "2026-03-01,inputs,10,x",
        ),
    )
    assert extra.status_code == 400
    assert "Unexpected header" in extra.data["detail"]
    assert "bogus" in extra.data["detail"]

    duplicate = upload(
        client,
        "expenses",
        csv_file(
            "duplicate.csv",
            "date,category,amount,date",
            "2026-03-01,inputs,10,2026-03-01",
        ),
    )
    assert duplicate.status_code == 400
    assert "Duplicate header" in duplicate.data["detail"]

    unsupported = upload(
        client,
        "expenses",
        SimpleUploadedFile(
            "expenses.txt",
            b"date,category,amount\n",
            content_type="text/plain",
        ),
    )
    assert unsupported.status_code == 400
    assert "Unsupported file type" in unsupported.data["detail"]


def test_valid_xlsx_preview_for_both_entity_types(client, setup):
    data = setup()
    item = make_item(client, data["unit"])

    expenses = upload(
        client,
        "expenses",
        xlsx_file(
            "expenses.xlsx",
            [
                ["date", "category", "amount", "supplier", "notes"],
                [datetime(2026, 3, 4), "inputs", 42.5, "Agro", "Seed"],
                ["2026-03-05", "labour", 10, None, None],
            ],
        ),
    )
    assert expenses.status_code == 200, expenses.data
    assert expenses.data["counts"] == {
        "total": 2,
        "valid": 2,
        "invalid": 0,
        "duplicate": 0,
    }
    assert expenses.data["validRows"][0]["date"] == "2026-03-04"
    assert expenses.data["validRows"][0]["amount"] == 42.5

    movements = upload(
        client,
        "inventory_movements",
        xlsx_file(
            "movements.xlsx",
            [
                ["item", "type", "quantity", "date", "note"],
                ["Nitrogen", "purchase", 5, datetime(2026, 3, 6), "Restock"],
            ],
        ),
    )
    assert movements.status_code == 200, movements.data
    assert movements.data["counts"]["valid"] == 1
    assert movements.data["validRows"][0]["itemId"] == item["id"]
    assert movements.data["validRows"][0]["date"] == "2026-03-06"


def test_invalid_xlsx_is_rejected_and_bad_rows_are_reported(client):
    malformed = upload(
        client,
        "expenses",
        SimpleUploadedFile(
            "broken.xlsx", b"not an excel workbook", content_type=""
        ),
    )
    assert malformed.status_code == 400
    assert malformed.data["field"] == "file"
    assert "Excel" in malformed.data["detail"]

    bad_rows = upload(
        client,
        "expenses",
        xlsx_file(
            "expenses.xlsx",
            [
                ["date", "category", "amount"],
                ["not-a-date", "rent", -5],
            ],
        ),
    )
    assert bad_rows.status_code == 200, bad_rows.data
    assert bad_rows.data["counts"]["invalid"] == 1
    assert {
        error["field"] for error in bad_rows.data["invalidRows"][0]["errors"]
    } == {"date", "category", "amount"}


def test_preview_endpoint_request_validation(client):
    missing_type = client.post(
        PREVIEW_URL,
        {"file": csv_file("expenses.csv", "date,category,amount")},
        format="multipart",
    )
    assert missing_type.status_code == 400
    assert missing_type.data["field"] == "entityType"

    missing_file = client.post(
        PREVIEW_URL, {"entityType": "expenses"}, format="multipart"
    )
    assert missing_file.status_code == 400
    assert missing_file.data["field"] == "file"

    unsupported = upload(
        client,
        "sales",
        csv_file("sales.csv", "date,category,amount"),
    )
    assert unsupported.status_code == 400
    assert unsupported.data["field"] == "entityType"


def test_preview_requires_authentication(anon):
    response = anon.post(
        PREVIEW_URL,
        {
            "entityType": "expenses",
            "file": csv_file("expenses.csv", "date,category,amount"),
        },
        format="multipart",
    )
    assert response.status_code == 401


def test_expenses_reject_unrepresentable_amounts(client):
    response = upload(
        client,
        "expenses",
        csv_file(
            "expenses.csv",
            "date,category,amount",
            "2026-03-01,inputs,1e100000",
            "2026-03-01,inputs,1.23456",
            "2026-03-01,inputs,10000000000",
            "2026-03-01,inputs,9999999999.9999",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["counts"] == {
        "total": 4,
        "valid": 1,
        "invalid": 3,
        "duplicate": 0,
    }
    errors = {row["row"]: row["errors"] for row in body["invalidRows"]}
    assert [error["field"] for error in errors[2]] == ["amount"]
    assert "exceed" in errors[2][0]["message"]
    assert [error["field"] for error in errors[3]] == ["amount"]
    assert "decimal places" in errors[3][0]["message"]
    assert [error["field"] for error in errors[4]] == ["amount"]
    assert "exceed" in errors[4][0]["message"]
    assert body["validRows"][0]["row"] == 5


def test_movements_reject_unrepresentable_quantities(client, setup):
    make_item(client, setup()["unit"])

    response = upload(
        client,
        "inventory_movements",
        csv_file(
            "movements.csv",
            "item,type,quantity,date",
            "Nitrogen,purchase,1e100000,2026-03-01",
            "Nitrogen,purchase,1.23456,2026-03-01",
            "Nitrogen,purchase,10000000000,2026-03-01",
            "Nitrogen,purchase,9999999999.9999,2026-03-01",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["counts"] == {
        "total": 4,
        "valid": 1,
        "invalid": 3,
        "duplicate": 0,
    }
    errors = {row["row"]: row["errors"] for row in body["invalidRows"]}
    assert [error["field"] for error in errors[2]] == ["quantity"]
    assert "exceed" in errors[2][0]["message"]
    assert [error["field"] for error in errors[3]] == ["quantity"]
    assert "decimal places" in errors[3][0]["message"]
    assert [error["field"] for error in errors[4]] == ["quantity"]
    assert "exceed" in errors[4][0]["message"]
    assert body["validRows"][0]["row"] == 5


def test_csv_blank_lines_preserve_source_row_numbers(client):
    response = upload(
        client,
        "expenses",
        csv_file(
            "expenses.csv",
            "date,category,amount",
            "",
            "2026-03-01,inputs,10",
            "",
            "not-a-date,inputs,10",
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["counts"] == {
        "total": 2,
        "valid": 1,
        "invalid": 1,
        "duplicate": 0,
    }
    assert body["validRows"][0]["row"] == 3
    assert body["invalidRows"][0]["row"] == 5


def test_xlsx_blank_rows_preserve_worksheet_row_numbers(client):
    response = upload(
        client,
        "expenses",
        xlsx_file(
            "expenses.xlsx",
            [
                ["date", "category", "amount"],
                ["2026-03-01", "inputs", 10],
                [None, None, None],
                ["not-a-date", "inputs", 10],
            ],
        ),
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["validRows"][0]["row"] == 2
    assert body["invalidRows"][0]["row"] == 4


def test_extra_row_values_report_structural_error_only(client):
    response = upload(
        client,
        "expenses",
        csv_file(
            "expenses.csv",
            "date,category,amount",
            "not-a-date,inputs,10,extra",
        ),
    )

    assert response.status_code == 200, response.data
    assert response.data["counts"] == {
        "total": 1,
        "valid": 0,
        "invalid": 1,
        "duplicate": 0,
    }
    row = response.data["invalidRows"][0]
    assert row["row"] == 2
    assert row["errors"] == [
        {
            "field": "row",
            "message": "Row has more values than the headers define.",
        }
    ]
