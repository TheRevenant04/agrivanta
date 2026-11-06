import pytest

from api.models import Expense, Farm, Supplier, User

DEFAULTS = {"inputs", "labour", "equipment", "overhead", "other"}


def other_farm():
    user = User.objects.create_user(
        email="other-expenses@agrivanta.test", password="OliveHarvest#42"
    )
    return Farm.objects.create(
        owner=user, name="Other Farm", reporting_currency="USD"
    )


def categories(client):
    response = client.get("/api/expense-categories")
    assert response.status_code == 200
    return {row["name"]: row for row in response.data}


def payload(client, **overrides):
    data = {
        "categoryId": categories(client)["inputs"]["id"],
        "amount": "120.50",
        "date": "2026-03-05",
    }
    data.update(overrides)
    return data


def test_default_categories_are_available(client):
    rows = categories(client)
    assert set(rows) == DEFAULTS
    assert all(row["isDefault"] for row in rows.values())


def test_custom_category_creation_and_detail(client):
    created = client.post(
        "/api/expense-categories", {"name": " Fuel "}, format="json"
    )
    assert created.status_code == 201
    assert created.data["name"] == "Fuel"
    assert created.data["isDefault"] is False
    detail = client.get(f"/api/expense-categories/{created.data['id']}")
    assert detail.status_code == 200
    assert detail.data == created.data
    assert "Fuel" in categories(client)


def test_max_length_category_is_preserved_in_expense(client):
    name = "é" * 255
    category = client.post(
        "/api/expense-categories", {"name": name}, format="json"
    )
    assert category.status_code == 201
    created = client.post(
        "/api/expenses",
        payload(client, categoryId=category.data["id"]),
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["category"] == name
    expense = Expense.objects.get(pk=created.data["id"])
    assert expense.category == name
    assert Expense._meta.get_field("category").max_length >= len(name)
    expense.full_clean()
    assert client.get(f"/api/expenses/{expense.id}").data["category"] == name


def test_category_name_over_max_length_is_rejected(client):
    response = client.post(
        "/api/expense-categories",
        {"name": "é" * 256},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == "name"
    assert "é" * 256 not in categories(client)


@pytest.mark.parametrize("name", [None, "", "  "])
def test_category_name_required(client, name):
    response = client.post(
        "/api/expense-categories", {"name": name}, format="json"
    )
    assert response.status_code == 400
    assert response.data["field"] == "name"


def test_duplicate_category_rejected_but_allowed_on_other_farm(client):
    assert client.post(
        "/api/expense-categories", {"name": "Fuel"}, format="json"
    ).status_code == 201
    for name in ("Fuel", "fuel", "Inputs"):
        response = client.post(
            "/api/expense-categories", {"name": name}, format="json"
        )
        assert response.status_code == 400
        assert response.data["field"] == "name"

    foreign = other_farm()
    foreign.expense_categories.create(name="Fuel")
    assert foreign.expense_categories.filter(name="Fuel").count() == 1


def test_categories_are_farm_isolated(client):
    foreign = other_farm()
    secret = foreign.expense_categories.create(name="Secret")
    assert "Secret" not in categories(client)
    detail = client.get(f"/api/expense-categories/{secret.id}")
    assert detail.status_code == 404


def test_expense_defaults_to_draft_with_optional_fields_omitted(client):
    response = client.post("/api/expenses", payload(client), format="json")
    assert response.status_code == 201, response.data
    assert response.data["status"] == "draft"
    assert response.data["category"] == "inputs"
    assert response.data["categoryId"] == categories(client)["inputs"]["id"]
    assert response.data["supplier"] is None
    assert response.data["supplierId"] is None
    assert response.data["attachmentReference"] is None
    assert response.data["amount"] == 120.5


def test_expense_defaults_to_draft_with_null_status(client):
    response = client.post(
        "/api/expenses", payload(client, status=None), format="json"
    )
    assert response.status_code == 201, response.data
    assert response.data["status"] == "draft"


def test_expense_with_supplier_attachment_and_posted_status(client):
    farm_id = client.get("/api/farm").data["id"]
    supplier = {
        "id": str(Supplier.objects.create(farm_id=farm_id, name="Agro Supply").id)
    }
    custom = client.post(
        "/api/expense-categories", {"name": "Fuel"}, format="json"
    ).data
    response = client.post(
        "/api/expenses",
        payload(
            client,
            categoryId=custom["id"],
            supplierId=supplier["id"],
            attachmentReference="receipt-42.pdf",
            status="posted",
        ),
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["category"] == "Fuel"
    assert response.data["supplier"] == "Agro Supply"
    assert response.data["supplierId"] == supplier["id"]
    assert response.data["attachmentReference"] == "receipt-42.pdf"
    assert response.data["status"] == "posted"


def test_expense_accepts_max_length_attachment_reference(client):
    attachment_reference = "a" * 500
    response = client.post(
        "/api/expenses",
        payload(client, attachmentReference=attachment_reference),
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["attachmentReference"] == attachment_reference
    expense = Expense.objects.get(pk=response.data["id"])
    assert expense.attachment_reference == attachment_reference


def test_expense_rejects_attachment_reference_over_max_length(client):
    response = client.post(
        "/api/expenses",
        payload(client, attachmentReference="a" * 501),
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == "attachmentReference"
    assert Expense.objects.count() == 0


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"categoryId": None}, "categoryId"),
        ({"amount": None}, "amount"),
        ({"amount": ""}, "amount"),
        ({"date": None}, "date"),
        ({"amount": "0"}, "amount"),
        ({"amount": "-5"}, "amount"),
        ({"status": "pending"}, "status"),
        ({"status": ""}, "status"),
        ({"status": "  "}, "status"),
    ],
)
def test_invalid_expense_input_rejected(client, overrides, field):
    response = client.post(
        "/api/expenses", payload(client, **overrides), format="json"
    )
    assert response.status_code == 400
    assert response.data["field"] == field
    assert Expense.objects.count() == 0


def test_expense_rejects_other_farm_category_and_supplier(client):
    foreign = other_farm()
    category = foreign.expense_categories.get(name="inputs")
    supplier = Supplier.objects.create(farm=foreign, name="Foreign")

    bad_category = client.post(
        "/api/expenses",
        payload(client, categoryId=str(category.id)),
        format="json",
    )
    assert bad_category.status_code == 404
    assert bad_category.data["field"] == "categoryId"

    bad_supplier = client.post(
        "/api/expenses",
        payload(client, supplierId=str(supplier.id)),
        format="json",
    )
    assert bad_supplier.status_code == 404
    assert bad_supplier.data["field"] == "supplierId"
    assert Expense.objects.count() == 0


def test_expense_list_and_detail_are_farm_scoped(client):
    assert client.get("/api/expenses").data == []
    foreign = other_farm()
    foreign_expense = Expense.objects.create(
        farm=foreign,
        category="inputs",
        amount="10",
        date="2026-03-01",
    )
    mine = client.post("/api/expenses", payload(client), format="json").data

    rows = client.get("/api/expenses").data
    assert [row["id"] for row in rows] == [mine["id"]]
    assert client.get(f"/api/expenses/{mine['id']}").data == mine
    assert client.get(f"/api/expenses/{foreign_expense.id}").status_code == 404


def test_draft_expense_can_be_edited_and_deleted(client):
    created = client.post(
        "/api/expenses", payload(client), format="json"
    ).data
    labour = categories(client)["labour"]["id"]
    edited = client.put(
        f"/api/expenses/{created['id']}",
        payload(
            client,
            categoryId=labour,
            amount="75",
            attachmentReference="inv-9",
        ),
        format="json",
    )
    assert edited.status_code == 200, edited.data
    assert edited.data["category"] == "labour"
    assert edited.data["amount"] == 75
    assert edited.data["status"] == "draft"
    assert client.get(f"/api/expenses/{created['id']}").data == edited.data

    assert client.delete(f"/api/expenses/{created['id']}").status_code == 204
    assert client.get(f"/api/expenses/{created['id']}").status_code == 404
    assert client.get("/api/expenses").data == []


def test_posted_expense_is_readable_but_not_editable_or_deletable(client):
    created = client.post(
        "/api/expenses", payload(client, status="posted"), format="json"
    ).data
    assert created["status"] == "posted"
    assert [row["id"] for row in client.get("/api/expenses").data] == [
        created["id"]
    ]
    assert client.get(f"/api/expenses/{created['id']}").data == created

    edit = client.put(
        f"/api/expenses/{created['id']}",
        payload(client, amount="1"),
        format="json",
    )
    assert edit.status_code == 400
    assert client.delete(f"/api/expenses/{created['id']}").status_code == 400
    assert Expense.objects.get(pk=created["id"]).amount == 120.5


def test_legacy_category_name_still_accepted(client):
    response = client.post(
        "/api/expenses",
        {"category": "overhead", "amount": "5", "date": "2026-03-05"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["category"] == "overhead"
    assert response.data["categoryId"] == categories(client)["overhead"]["id"]
