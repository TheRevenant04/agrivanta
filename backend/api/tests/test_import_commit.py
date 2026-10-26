import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import (
    Expense,
    ImportCommit,
    ImportPreview,
    StockMovement,
)


PREVIEW_URL = "/api/imports/preview"
COMMIT_URL = "/api/imports/commit"


def csv_file(name, *lines):
    return SimpleUploadedFile(
        name,
        ("\n".join(lines) + "\n").encode("utf-8"),
        content_type="text/csv",
    )


def preview(client, entity_type, headers, *rows):
    return client.post(
        PREVIEW_URL,
        {
            "entityType": entity_type,
            "file": csv_file(f"{entity_type}.csv", headers, *rows),
        },
        format="multipart",
    )


def expenses_preview(client, *rows):
    return preview(
        client,
        "expenses",
        "date,category,amount,supplier,notes,cycleId",
        *rows,
    )


def movements_preview(client, *rows):
    return preview(
        client,
        "inventory_movements",
        "item,type,quantity,date,note",
        *rows,
    )


def commit(client, token, confirmed_rows, corrections=None):
    payload = {"token": token, "confirmedRows": confirmed_rows}
    if corrections is not None:
        payload["corrections"] = corrections
    return client.post(COMMIT_URL, payload, format="json")


def make_item(client, unit, name="Nitrogen"):
    response = client.post(
        "/api/inventory-items",
        {"name": name, "unitId": unit["id"], "reorderLevel": "2"},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def test_preview_issues_token_and_imports_nothing(client):
    response = expenses_preview(
        client,
        "2026-03-01,inputs,250.50,Agro Supply,Seed purchase,",
        "2026-03-02,labour,100,,,",
    )

    assert response.status_code == 200, response.data
    body = response.data
    assert body["previewToken"]
    assert body["expiresAt"]
    record = ImportPreview.objects.get(token=body["previewToken"])
    assert record.consumed_at is None
    assert record.expires_at > timezone.now()
    assert record.entity_type == "expenses"
    assert [row["row"] for row in record.rows] == [2, 3]
    assert Expense.objects.count() == 0
    assert StockMovement.objects.count() == 0
    assert ImportCommit.objects.count() == 0


def test_valid_commit_imports_only_confirmed_rows_and_audits(
    client, session
):
    data = expenses_preview(
        client,
        "2026-03-01,inputs,250.50,Agro Supply,Seed purchase,",
        "2026-03-02,labour,100,,,",
    ).data
    token = data["previewToken"]

    response = commit(client, token, [data["validRows"][0]["row"]])

    assert response.status_code == 201, response.data
    assert response.data["imported"][0]["row"] == 2
    assert response.data["counts"] == {
        "confirmed": 1,
        "imported": 1,
        "skipped": 1,
    }
    assert Expense.objects.count() == 1
    expense = Expense.objects.get()
    assert expense.category == "inputs"
    assert expense.amount == Decimal("250.5000")
    assert expense.date == date(2026, 3, 1)
    assert expense.supplier == "Agro Supply"
    assert expense.notes == "Seed purchase"
    assert expense.status == "draft"

    audit = ImportCommit.objects.get()
    assert str(audit.actor_id) == session["user"]["id"]
    assert str(audit.preview_token) == token
    assert audit.entity_type == "expenses"
    assert audit.entity_counts == {"expenses": 1}
    assert audit.created_at is not None
    assert response.data["audit"]["id"] == str(audit.id)
    assert response.data["audit"]["actorId"] == session["user"]["id"]
    assert response.data["audit"]["entityCounts"] == {"expenses": 1}
    assert response.data["audit"]["previewToken"] == token

    record = ImportPreview.objects.get(token=token)
    assert record.consumed_at is not None


def test_partial_import_only_confirmed_rows(client):
    data = expenses_preview(
        client,
        "2026-03-01,inputs,10,,,",
        "2026-03-02,labour,20,,,",
        "2026-03-03,equipment,30,,,",
    ).data
    token = data["previewToken"]

    response = commit(
        client, token, [data["validRows"][0]["row"], data["validRows"][2]["row"]]
    )

    assert response.status_code == 201, response.data
    assert [row["row"] for row in response.data["imported"]] == [2, 4]
    assert Expense.objects.count() == 2
    assert list(
        Expense.objects.order_by("date").values_list("amount", flat=True)
    ) == [Decimal("10.0000"), Decimal("30.0000")]
    assert response.data["counts"] == {
        "confirmed": 2,
        "imported": 2,
        "skipped": 1,
    }


def test_corrected_row_is_revalidated_and_unconfirmed_rows_skipped(client):
    data = expenses_preview(
        client,
        "2026-03-01,inputs,250.50,Agro Supply,Seed purchase,",
        "2026-03-02,labour,100,,,",
        "2026-03-03,equipment,50,,,",
    ).data
    token = data["previewToken"]

    response = commit(
        client,
        token,
        [data["validRows"][0]["row"]],
        {
            str(data["validRows"][0]["row"]): {
                "amount": "300.25",
                "supplier": "Corrected Ltd",
            }
        },
    )

    assert response.status_code == 201, response.data
    assert Expense.objects.count() == 1
    expense = Expense.objects.get()
    assert expense.amount == Decimal("300.2500")
    assert expense.supplier == "Corrected Ltd"
    assert expense.date == date(2026, 3, 1)
    assert not Expense.objects.filter(date=date(2026, 3, 2)).exists()
    assert not Expense.objects.filter(date=date(2026, 3, 3)).exists()


def test_per_entry_correction_is_supported(client):
    data = expenses_preview(
        client,
        "2026-03-01,inputs,10,,,",
        "2026-03-02,labour,20,,,",
    ).data

    response = commit(
        client,
        data["previewToken"],
        [
            {
                "row": data["validRows"][0]["row"],
                "values": {"amount": "12.5"},
            }
        ],
    )

    assert response.status_code == 201, response.data
    assert Expense.objects.get().amount == Decimal("12.5000")


def test_empty_confirmation_is_rejected_without_writes(client):
    data = expenses_preview(
        client,
        "2026-03-01,inputs,10,,,",
        "2026-03-02,labour,20,,,",
    ).data
    token = data["previewToken"]

    response = commit(client, token, [])

    assert response.status_code == 400
    assert response.data["field"] == "confirmedRows"
    assert "at least one" in response.data["detail"]
    assert Expense.objects.count() == 0
    assert ImportCommit.objects.count() == 0
    record = ImportPreview.objects.get(token=token)
    assert record.consumed_at is None

    retry = commit(client, token, [data["validRows"][0]["row"]])
    assert retry.status_code == 201, retry.data
    assert Expense.objects.count() == 1


def test_missing_token_is_rejected(client):
    response = client.post(
        COMMIT_URL, {"confirmedRows": [2]}, format="json"
    )

    assert response.status_code == 400
    assert response.data["field"] == "token"
    assert "required" in response.data["detail"]
    assert Expense.objects.count() == 0


def test_invalid_token_is_rejected(client):
    for token in ("not-a-token", str(uuid.uuid4())):
        response = commit(client, token, [2])
        assert response.status_code == 400
        assert response.data["field"] == "token"
        assert "invalid" in response.data["detail"]

    assert Expense.objects.count() == 0
    assert ImportCommit.objects.count() == 0


def test_expired_token_is_rejected(client):
    data = expenses_preview(client, "2026-03-01,inputs,10,,,").data
    token = data["previewToken"]
    record = ImportPreview.objects.get(token=token)
    record.expires_at = timezone.now() - timedelta(seconds=1)
    record.save(update_fields=["expires_at"])

    response = commit(client, token, [data["validRows"][0]["row"]])

    assert response.status_code == 400
    assert response.data["field"] == "token"
    assert "expired" in response.data["detail"]
    assert Expense.objects.count() == 0
    assert ImportCommit.objects.count() == 0
    record.refresh_from_db()
    assert record.consumed_at is None


def test_replaying_a_committed_token_is_rejected(client):
    data = expenses_preview(
        client,
        "2026-03-01,inputs,10,,,",
        "2026-03-02,labour,20,,,",
    ).data
    token = data["previewToken"]
    first = commit(client, token, [data["validRows"][0]["row"]])
    assert first.status_code == 201, first.data

    replay = commit(client, token, [data["validRows"][1]["row"]])

    assert replay.status_code == 409
    assert replay.data["field"] == "token"
    assert "already" in replay.data["detail"]
    assert Expense.objects.count() == 1
    assert ImportCommit.objects.count() == 1


def test_unknown_row_is_rejected_without_writes(client):
    data = expenses_preview(client, "2026-03-01,inputs,10,,,").data
    token = data["previewToken"]

    response = commit(client, token, [999])

    assert response.status_code == 400
    assert response.data["field"] == "confirmedRows"
    assert "not part of this preview" in response.data["detail"]
    assert Expense.objects.count() == 0
    assert ImportCommit.objects.count() == 0
    record = ImportPreview.objects.get(token=token)
    assert record.consumed_at is None


def test_invalid_correction_is_rejected_without_consuming_token(client):
    data = expenses_preview(client, "2026-03-01,inputs,10,,,").data
    token = data["previewToken"]

    response = commit(
        client,
        token,
        [data["validRows"][0]["row"]],
        {str(data["validRows"][0]["row"]): {"amount": "-5"}},
    )

    assert response.status_code == 400
    assert response.data["field"] == "confirmedRows"
    assert "amount" in response.data["detail"]
    assert Expense.objects.count() == 0
    assert ImportCommit.objects.count() == 0
    record = ImportPreview.objects.get(token=token)
    assert record.consumed_at is None

    retry = commit(client, token, [data["validRows"][0]["row"]])
    assert retry.status_code == 201, retry.data
    assert Expense.objects.get().amount == Decimal("10.0000")


def test_commit_inventory_movements(client, setup):
    item = make_item(client, setup()["unit"])
    data = movements_preview(
        client,
        "Nitrogen,purchase,10,2026-03-02,Initial stock",
        "Nitrogen,usage,3,2026-03-03,",
    ).data

    response = commit(client, data["previewToken"], [data["validRows"][0]["row"]])

    assert response.status_code == 201, response.data
    assert StockMovement.objects.count() == 1
    movement = StockMovement.objects.get()
    assert str(movement.item_id) == item["id"]
    assert movement.type == "purchase"
    assert movement.quantity == Decimal("10.0000")
    assert movement.date == date(2026, 3, 2)
    assert movement.note == "Initial stock"
    audit = ImportCommit.objects.get()
    assert audit.entity_type == "inventory_movements"
    assert audit.entity_counts == {"inventory_movements": 1}


def test_preview_token_is_scoped_to_the_farm(client):
    data = expenses_preview(client, "2026-03-01,inputs,10,,,").data
    token = data["previewToken"]

    other = APIClient()
    registered = other.post(
        "/api/auth/register",
        {
            "name": "Other Owner",
            "email": "other-import@agrivanta.test",
            "password": "password123",
        },
        format="json",
    )
    assert registered.status_code == 201, registered.data
    other.credentials(
        HTTP_AUTHORIZATION=f"Bearer {registered.data['token']}"
    )

    response = other.post(
        COMMIT_URL,
        {"token": token, "confirmedRows": [data["validRows"][0]["row"]]},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["field"] == "token"
    assert "invalid" in response.data["detail"]
    assert Expense.objects.count() == 0

    retry = commit(client, token, [data["validRows"][0]["row"]])
    assert retry.status_code == 201, retry.data


def test_commit_requires_authentication(anon):
    response = anon.post(
        COMMIT_URL, {"token": str(uuid.uuid4()), "confirmedRows": [2]},
        format="json",
    )

    assert response.status_code == 401
