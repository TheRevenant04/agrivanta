from django.core.files.uploadedfile import SimpleUploadedFile


def make_item(client, unit):
    response = client.post(
        "/api/inventory-items",
        {"name": "Nitrogen", "unitId": unit["id"], "reorderLevel": "2"},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def test_stock_movements_track_current_quantity(client, setup):
    data = setup()
    item = make_item(client, data["unit"])

    purchase = client.post(
        f"/api/inventory-items/{item['id']}/movements",
        {
            "itemId": item["id"],
            "type": "purchase",
            "quantity": "10",
            "date": "2026-03-02",
            "note": "Initial stock",
        },
        format="json",
    )
    assert purchase.status_code == 201
    assert purchase.data["note"] == "Initial stock"

    usage = client.post(
        f"/api/inventory-items/{item['id']}/movements",
        {
            "itemId": item["id"],
            "type": "usage",
            "quantity": 3,
            "date": "2026-03-03",
        },
        format="json",
    )
    assert usage.status_code == 201

    adjustment = client.post(
        f"/api/inventory-items/{item['id']}/movements",
        {
            "itemId": item["id"],
            "type": "adjustment",
            "quantity": "-2",
            "date": "2026-03-04",
        },
        format="json",
    )
    assert adjustment.status_code == 201

    detail = client.get("/api/inventory-items").data[0]
    assert detail["currentQuantity"] == 5

    movements = client.get(
        f"/api/inventory-items/{item['id']}/movements"
    )
    assert movements.status_code == 200
    assert [row["type"] for row in movements.data] == [
        "purchase",
        "usage",
        "adjustment",
    ]

    all_movements = client.get("/api/stock-movements")
    assert len(all_movements.data) == 3


def test_usage_cannot_drive_stock_negative(client, setup):
    item = make_item(client, setup()["unit"])

    response = client.post(
        f"/api/inventory-items/{item['id']}/movements",
        {
            "itemId": item["id"],
            "type": "usage",
            "quantity": "1",
            "date": "2026-03-01",
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == "quantity"


def test_movement_validation(client, setup):
    item = make_item(client, setup()["unit"])
    url = f"/api/inventory-items/{item['id']}/movements"

    bad_type = client.post(
        url,
        {"itemId": item["id"], "type": "waste", "quantity": "1"},
        format="json",
    )
    assert bad_type.status_code == 400
    assert bad_type.data["field"] == "type"

    bad_quantity = client.post(
        url,
        {
            "itemId": item["id"],
            "type": "purchase",
            "quantity": "nope",
        },
        format="json",
    )
    assert bad_quantity.status_code == 400
    assert bad_quantity.data["field"] == "quantity"

    zero_adjustment = client.post(
        url,
        {"itemId": item["id"], "type": "adjustment", "quantity": "0"},
        format="json",
    )
    assert zero_adjustment.status_code == 400
    assert zero_adjustment.data["field"] == "quantity"

    missing_item_id = client.post(
        url, {"type": "purchase", "quantity": "1"}, format="json"
    )
    assert missing_item_id.status_code == 400
    assert missing_item_id.data["field"] == "itemId"

    mismatched_item_id = client.post(
        url,
        {
            "itemId": "00000000-0000-0000-0000-000000000000",
            "type": "purchase",
            "quantity": "1",
        },
        format="json",
    )
    assert mismatched_item_id.status_code == 400
    assert mismatched_item_id.data["field"] == "itemId"

    missing_item = client.post(
        "/api/inventory-items/does-not-exist/movements",
        {"type": "purchase", "quantity": "1"},
        format="json",
    )
    assert missing_item.status_code == 404


def test_inventory_item_can_be_updated(client, setup):
    data = setup()
    item = make_item(client, data["unit"])

    updated = client.put(
        f"/api/inventory-items/{item['id']}",
        {"name": "Urea", "unitId": data["unit"]["id"], "reorderLevel": "5"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["name"] == "Urea"
    assert updated.data["reorderLevel"] == 5


def test_expense_draft_lifecycle_and_posted_immutability(client):
    created = client.post(
        "/api/expenses",
        {
            "category": "inputs",
            "amount": "250.50",
            "date": "2026-03-05",
            "supplier": "Agro Supply",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["status"] == "draft"
    assert created.data["amount"] == 250.5
    assert created.data["attachments"] == []

    edited = client.put(
        f"/api/expenses/{created.data['id']}",
        {
            "category": "labour",
            "amount": 300,
            "date": "2026-03-06",
            "supplier": "",
        },
        format="json",
    )
    assert edited.status_code == 200
    assert edited.data["category"] == "labour"
    assert edited.data["supplier"] is None

    posted = client.post(f"/api/expenses/{created.data['id']}/post")
    assert posted.status_code == 200
    assert posted.data["status"] == "posted"

    reject_edit = client.put(
        f"/api/expenses/{created.data['id']}",
        {
            "category": "labour",
            "amount": 350,
            "date": "2026-03-06",
        },
        format="json",
    )
    assert reject_edit.status_code == 400

    reject_delete = client.delete(f"/api/expenses/{created.data['id']}")
    assert reject_delete.status_code == 400

    reject_attachment = client.post(
        f"/api/expenses/{created.data['id']}/attachments",
        {
            "file": SimpleUploadedFile(
                "receipt.txt", b"receipt", content_type="text/plain"
            )
        },
        format="multipart",
    )
    assert reject_attachment.status_code == 400


def test_draft_expense_accepts_attachments_and_deletion(client, monkeypatch):
    from django.core.files.storage import InMemoryStorage
    from api.models import Attachment

    monkeypatch.setattr(Attachment._meta.get_field("private_file"), "storage", InMemoryStorage())
    created = client.post(
        "/api/expenses",
        {"category": "overhead", "amount": 90, "date": "2026-03-07"},
        format="json",
    ).data

    upload = client.post(
        f"/api/expenses/{created['id']}/attachments",
        {
            "file": SimpleUploadedFile(
                "receipt.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"
            )
        },
        format="multipart",
    )
    assert upload.status_code == 201
    assert upload.data["name"] == "receipt.pdf"
    assert "url" not in upload.data

    listing = client.get("/api/expenses")
    assert len(listing.data[0]["attachments"]) == 1

    deleted = client.delete(f"/api/expenses/{created['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/expenses").data == []


def test_expense_validation(client):
    bad_category = client.post(
        "/api/expenses",
        {"category": "rent", "amount": 10, "date": "2026-03-01"},
        format="json",
    )
    assert bad_category.status_code == 400
    assert bad_category.data["field"] == "category"

    bad_amount = client.post(
        "/api/expenses",
        {"category": "other", "amount": "ten", "date": "2026-03-01"},
        format="json",
    )
    assert bad_amount.status_code == 400
    assert bad_amount.data["field"] == "amount"

    bad_date = client.post(
        "/api/expenses",
        {"category": "other", "amount": 10, "date": "2026-02-30"},
        format="json",
    )
    assert bad_date.status_code == 400
    assert bad_date.data["field"] == "date"


def test_payments_link_to_expenses(client):
    expense = client.post(
        "/api/expenses",
        {"category": "inputs", "amount": 100, "date": "2026-03-08"},
        format="json",
    ).data

    created = client.post(
        "/api/payments",
        {
            "type": "paid",
            "amount": "100",
            "date": "2026-03-09",
            "linkedExpenseId": expense["id"],
            "reference": "INV-1",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["linkedExpenseId"] == expense["id"]
    assert created.data["linkedSaleId"] is None
    assert created.data["reference"] == "INV-1"

    bad_type = client.post(
        "/api/payments",
        {"type": "refund", "amount": 10, "date": "2026-03-09"},
        format="json",
    )
    assert bad_type.status_code == 400
    assert bad_type.data["field"] == "type"

    unknown_expense = client.post(
        "/api/payments",
        {
            "type": "paid",
            "amount": 10,
            "date": "2026-03-09",
            "linkedExpenseId": "00000000-0000-0000-0000-000000000000",
        },
        format="json",
    )
    assert unknown_expense.status_code == 400
    assert unknown_expense.data["field"] == "linkedExpenseId"

    assert len(client.get("/api/payments").data) == 1
