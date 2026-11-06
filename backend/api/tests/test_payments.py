from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Payment

PAYMENTS = "/api/payments"


def make_user_client(email):
    client = APIClient()
    response = client.post(
        "/api/auth/register",
        {
            "name": "Other Owner",
            "email": email,
            "password": "OliveHarvest#42",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {response.data['token']}"
    )
    return client


def make_expense(client):
    response = client.post(
        "/api/expenses",
        {"category": "inputs", "amount": 100, "date": "2026-03-08"},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def make_sale(client, built):
    harvest = client.post(
        "/api/harvests",
        {
            "cycleId": built["cycle"]["id"],
            "quantity": "100",
            "unitId": built["unit"]["id"],
            "date": "2026-08-01",
        },
        format="json",
    ).data
    customer = client.get("/api/customers").data[0]
    response = client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest["id"],
            "quantity": "10",
            "unitPrice": "2",
            "date": "2026-08-05",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def payload(**overrides):
    body = {"type": "received", "amount": "25.50", "date": "2026-08-10"}
    body.update(overrides)
    return body


def post(client, **overrides):
    return client.post(PAYMENTS, payload(**overrides), format="json")


def test_standalone_payment_crud(client):
    assert client.get(PAYMENTS).status_code == 200
    assert client.get(PAYMENTS).data == []

    created = post(client, reference="CASH-1")
    assert created.status_code == 201
    assert created.data["type"] == "received"
    assert created.data["amount"] == 25.5
    assert created.data["date"] == "2026-08-10"
    assert created.data["linkedSaleId"] is None
    assert created.data["linkedExpenseId"] is None
    assert created.data["reference"] == "CASH-1"
    pid = created.data["id"]

    assert client.get(PAYMENTS).data[0]["id"] == pid
    detail = client.get(f"{PAYMENTS}/{pid}")
    assert detail.status_code == 200
    assert detail.data["linkedSaleId"] is None

    assert client.put(
        f"{PAYMENTS}/{pid}", payload(amount="30"), format="json"
    ).status_code == 409
    assert client.patch(
        f"{PAYMENTS}/{pid}", {"reference": "R-9"}, format="json"
    ).status_code == 409
    assert client.delete(f"{PAYMENTS}/{pid}").status_code == 409
    assert client.get(f"{PAYMENTS}/{pid}").data == detail.data


def test_received_payment_links_to_sale(client, cycle):
    sale = make_sale(client, cycle())
    created = post(client, linkedSaleId=sale["id"])
    assert created.status_code == 201
    assert created.data["linkedSaleId"] == sale["id"]
    assert created.data["linkedExpenseId"] is None
    detail = client.get(f"{PAYMENTS}/{created.data['id']}")
    assert detail.data["linkedSaleId"] == sale["id"]


def test_paid_payment_links_to_expense(client):
    expense = make_expense(client)
    created = post(client, type="paid", linkedExpenseId=expense["id"])
    assert created.status_code == 201
    assert created.data["linkedExpenseId"] == expense["id"]
    assert created.data["linkedSaleId"] is None


def test_invalid_link_combinations_are_rejected(client, cycle):
    expense = make_expense(client)
    sale = make_sale(client, cycle())

    both = post(
        client,
        linkedSaleId=sale["id"],
        linkedExpenseId=expense["id"],
    )
    received_expense = post(client, linkedExpenseId=expense["id"])
    paid_sale = post(client, type="paid", linkedSaleId=sale["id"])

    for response in (both, received_expense, paid_sale):
        assert response.status_code == 400
        assert "field" in response.data
    assert received_expense.data["field"] == "linkedExpenseId"
    assert paid_sale.data["field"] == "linkedSaleId"
    assert Payment.objects.count() == 0

    existing = post(client).data["id"]
    update = client.put(
        f"{PAYMENTS}/{existing}",
        payload(type="paid", linkedSaleId=sale["id"]),
        format="json",
    )
    assert update.status_code == 409
    assert client.get(f"{PAYMENTS}/{existing}").data["type"] == "received"


@pytest.mark.parametrize("field", ["type", "amount", "date"])
def test_required_fields(client, field):
    body = payload()
    del body[field]
    response = client.post(PAYMENTS, body, format="json")
    assert response.status_code == 400
    assert response.data["field"] == field
    assert Payment.objects.count() == 0


@pytest.mark.parametrize("value", ["refund", "", "RECEIVED", 5])
def test_invalid_type(client, value):
    response = post(client, type=value)
    assert response.status_code == 400
    assert response.data["field"] == "type"


@pytest.mark.parametrize(
    "amount",
    [0, "0", "-1", "abc", "NaN", "Infinity", "-Infinity", "1.00001",
     "100000000000", True, None, ""],
)
def test_invalid_amounts(client, amount):
    response = post(client, amount=amount)
    assert response.status_code == 400
    assert response.data["field"] == "amount"
    assert Payment.objects.count() == 0


def test_amount_boundaries(client):
    smallest = post(client, amount="0.0001")
    assert smallest.status_code == 201
    assert smallest.data["amount"] == 0.0001
    largest = post(client, amount="9999999999.9999")
    assert largest.status_code == 201


@pytest.mark.parametrize(
    "value", ["", "not-a-date", "2026-02-30", "2026-13-01", None]
)
def test_invalid_dates(client, value):
    response = post(client, date=value)
    assert response.status_code == 400
    assert response.data["field"] == "date"
    assert Payment.objects.count() == 0


def test_date_boundaries(client):
    today = timezone.localdate()
    assert post(client, date=today.isoformat()).status_code == 201
    assert post(client, date="2000-01-01").status_code == 201
    future = post(client, date=(today + timedelta(days=1)).isoformat())
    assert future.status_code == 400
    assert future.data["field"] == "date"


def test_reference_optional_and_duplicable(client):
    omitted = post(client)
    empty = post(client, reference="")
    assert omitted.data["reference"] is None
    assert empty.data["reference"] is None
    first = post(client, reference="INV-7")
    second = post(client, reference="INV-7")
    assert first.data["reference"] == second.data["reference"] == "INV-7"
    assert first.data["id"] != second.data["id"]


@pytest.mark.parametrize("reference_length", [255, 256])
def test_reference_length_is_validated_on_create(client, reference_length):
    reference = "R" * reference_length
    response = post(client, reference=reference)

    if reference_length > 255:
        assert response.status_code == 400
        assert response.data["field"] == "reference"
        assert Payment.objects.count() == 0
    else:
        assert response.status_code == 201
        assert response.data["reference"] == reference
        assert Payment.objects.get(pk=response.data["id"]).reference == (
            reference
        )


def test_identical_submissions_create_distinct_records(client):
    first = post(client)
    second = post(client)
    assert first.status_code == second.status_code == 201
    assert first.data["id"] != second.data["id"]
    assert len(client.get(PAYMENTS).data) == 2


def test_cross_farm_links_are_rejected(client, cycle):
    other = make_user_client("payments-other@agrivanta.test")
    foreign_expense = make_expense(other)
    other_built = {}
    for name, path, body in (
        ("field", "/api/fields", {"name": "F", "area": "1"}),
        ("crop", "/api/crops", {"name": "Corn"}),
        ("unit", "/api/units", {"name": "kg", "baseMeasure": "mass"}),
    ):
        other_built[name] = other.post(path, body, format="json").data
    variety = other.post(
        "/api/varieties",
        {"cropId": other_built["crop"]["id"], "name": "V"},
        format="json",
    ).data
    other_built["cycle"] = other.post(
        "/api/crop-cycles",
        {
            "fieldId": other_built["field"]["id"],
            "cropId": other_built["crop"]["id"],
            "varietyId": variety["id"],
            "cycleType": "annual",
            "startDate": "2026-03-01",
        },
        format="json",
    ).data
    foreign_sale = make_sale(other, other_built)

    expense = post(
        client, type="paid", linkedExpenseId=foreign_expense["id"]
    )
    sale = post(client, linkedSaleId=foreign_sale["id"])
    assert expense.status_code == 400
    assert expense.data["field"] == "linkedExpenseId"
    assert sale.status_code == 400
    assert sale.data["field"] == "linkedSaleId"
    assert Payment.objects.count() == 0


def test_payments_are_farm_isolated(client):
    other = make_user_client("payments-isolation@agrivanta.test")
    mine = post(client, reference="mine").data
    theirs = post(other, reference="theirs").data

    assert [p["id"] for p in client.get(PAYMENTS).data] == [mine["id"]]
    assert [p["id"] for p in other.get(PAYMENTS).data] == [theirs["id"]]

    url = f"{PAYMENTS}/{theirs['id']}"
    assert client.get(url).status_code == 404
    assert (
        client.put(url, payload(amount="1"), format="json").status_code
        == 404
    )
    assert (
        client.patch(url, {"amount": "1"}, format="json").status_code
        == 404
    )
    assert client.delete(url).status_code == 404
    assert other.get(url).data["amount"] == 25.5
    assert other.get(url).data["reference"] == "theirs"


def test_unknown_payment_returns_404(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"{PAYMENTS}/{missing}").status_code == 404
    assert client.get(f"{PAYMENTS}/not-a-uuid").status_code == 404


def test_payments_require_authentication(anon):
    assert anon.get(PAYMENTS).status_code == 401
    assert anon.post(PAYMENTS, payload(), format="json").status_code == 401
