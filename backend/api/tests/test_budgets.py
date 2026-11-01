from rest_framework.test import APIClient

BUDGETS = "/api/budgets"


def make_user_client(email, name="Other Owner"):
    client = APIClient()
    response = client.post(
        "/api/auth/register",
        {
            "name": name,
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


def make_cycle(client, label):
    field = client.post(
        "/api/fields",
        {"name": f"{label} field", "area": "4"},
        format="json",
    )
    crop = client.post(
        "/api/crops", {"name": f"{label} crop"}, format="json"
    )
    variety = client.post(
        "/api/varieties",
        {"cropId": crop.data["id"], "name": f"{label} variety"},
        format="json",
    )
    cycle = client.post(
        "/api/crop-cycles",
        {
            "fieldId": field.data["id"],
            "cropId": crop.data["id"],
            "varietyId": variety.data["id"],
            "startDate": "2026-03-01",
        },
        format="json",
    )
    assert field.status_code == 201, field.data
    assert crop.status_code == 201, crop.data
    assert variety.status_code == 201, variety.data
    assert cycle.status_code == 201, cycle.data
    return cycle.data


def create_budget(client, **payload):
    response = client.post(BUDGETS, payload, format="json")
    assert response.status_code == 201, response.data
    return response.data


def test_create_budget_at_crop_cycle_level(client, cycle):
    data = cycle()
    budget = create_budget(
        client,
        amount="1200.50",
        cycleId=data["cycle"]["id"],
    )

    assert budget["id"]
    assert budget["cycleId"] == data["cycle"]["id"]
    assert budget["category"] is None
    assert budget["amount"] == 1200.5
    assert budget["periodStart"] is None
    assert budget["periodEnd"] is None


def test_create_budget_at_farm_scope(client):
    budget = create_budget(client, amount=5000)

    assert budget["cycleId"] is None
    assert budget["category"] is None
    assert budget["amount"] == 5000
    assert budget["periodStart"] is None
    assert budget["periodEnd"] is None

    listing = client.get(BUDGETS)
    assert listing.status_code == 200
    assert listing.data == [budget]


def test_create_budget_at_category_level(client, cycle):
    data = cycle()

    with_cycle = create_budget(
        client,
        amount="300",
        cycleId=data["cycle"]["id"],
        category="inputs",
    )
    assert with_cycle["cycleId"] == data["cycle"]["id"]
    assert with_cycle["category"] == "inputs"

    farm_scope = create_budget(
        client, amount="150", category="labour"
    )
    assert farm_scope["cycleId"] is None
    assert farm_scope["category"] == "labour"


def test_create_budget_validates_amount(client):
    missing = client.post(BUDGETS, {}, format="json")
    assert missing.status_code == 400
    assert missing.data["field"] == "amount"

    non_numeric = client.post(BUDGETS, {"amount": "lots"}, format="json")
    assert non_numeric.status_code == 400
    assert non_numeric.data["field"] == "amount"

    zero = client.post(BUDGETS, {"amount": 0}, format="json")
    assert zero.status_code == 400
    assert zero.data["field"] == "amount"

    negative = client.post(BUDGETS, {"amount": "-10"}, format="json")
    assert negative.status_code == 400
    assert negative.data["field"] == "amount"


def test_create_budget_rejects_invalid_category(client):
    response = client.post(
        BUDGETS, {"amount": 100, "category": "rent"}, format="json"
    )
    assert response.status_code == 400
    assert response.data["field"] == "category"


def test_create_budget_rejects_unknown_cycle(client):
    response = client.post(
        BUDGETS,
        {
            "amount": 100,
            "cycleId": "00000000-0000-0000-0000-000000000000",
        },
        format="json",
    )
    assert response.status_code == 404
    assert response.data["field"] == "cycleId"


def test_create_budget_rejects_foreign_cycle(client):
    other = make_user_client("cycle-owner@agrivanta.test")
    foreign_cycle = make_cycle(other, "Foreign")

    response = client.post(
        BUDGETS,
        {"amount": 100, "cycleId": foreign_cycle["id"]},
        format="json",
    )
    assert response.status_code == 404
    assert response.data["field"] == "cycleId"


def test_create_budget_rejects_period_end_before_start(client):
    response = client.post(
        BUDGETS,
        {
            "amount": 100,
            "periodStart": "2026-04-01",
            "periodEnd": "2026-03-31",
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == "periodEnd"


def test_update_budget_rejects_period_end_before_start(client):
    budget = create_budget(
        client,
        amount=100,
        periodStart="2026-03-01",
        periodEnd="2026-03-31",
    )

    response = client.put(
        f"{BUDGETS}/{budget['id']}",
        {
            "amount": 100,
            "periodStart": "2026-04-01",
            "periodEnd": "2026-03-31",
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == "periodEnd"


def test_update_budget_rejects_unknown_cycle(client):
    budget = create_budget(client, amount=100)

    response = client.put(
        f"{BUDGETS}/{budget['id']}",
        {
            "amount": 100,
            "cycleId": "00000000-0000-0000-0000-000000000000",
        },
        format="json",
    )
    assert response.status_code == 404
    assert response.data["field"] == "cycleId"


def test_list_budgets_is_scoped_and_supports_filters(client):
    assert client.get(BUDGETS).data == []

    first = make_cycle(client, "Spring")
    second = make_cycle(client, "Autumn")
    on_first = create_budget(
        client,
        amount=100,
        cycleId=first["id"],
        category="inputs",
    )
    on_second = create_budget(
        client,
        amount=200,
        cycleId=second["id"],
        category="labour",
    )
    farm_scope = create_budget(client, amount=300)

    everything = client.get(BUDGETS)
    assert everything.status_code == 200
    assert {row["id"] for row in everything.data} == {
        on_first["id"],
        on_second["id"],
        farm_scope["id"],
    }

    by_cycle = client.get(f"{BUDGETS}?cycle={first['id']}")
    assert [row["id"] for row in by_cycle.data] == [on_first["id"]]

    by_category = client.get(f"{BUDGETS}?category=inputs")
    assert [row["id"] for row in by_category.data] == [on_first["id"]]

    by_both = client.get(
        f"{BUDGETS}?cycle={second['id']}&category=labour"
    )
    assert [row["id"] for row in by_both.data] == [on_second["id"]]

    other = make_user_client("budget-owner@agrivanta.test")
    other_budget = create_budget(other, amount=999)
    assert client.get(BUDGETS).data == everything.data
    assert client.get(f"{BUDGETS}/{other_budget['id']}").status_code == 404


def test_budget_detail_returns_404_for_unknown_id(client):
    response = client.get(
        f"{BUDGETS}/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


def test_update_budget_round_trip(client, cycle):
    data = cycle()
    budget = create_budget(
        client,
        amount="750.25",
        cycleId=data["cycle"]["id"],
        category="equipment",
        periodStart="2026-03-01",
        periodEnd="2026-05-31",
    )

    round_trip = client.put(
        f"{BUDGETS}/{budget['id']}",
        {
            "amount": budget["amount"],
            "cycleId": budget["cycleId"],
            "category": budget["category"],
            "periodStart": budget["periodStart"],
            "periodEnd": budget["periodEnd"],
        },
        format="json",
    )
    assert round_trip.status_code == 200
    assert round_trip.data == budget

    updated = client.put(
        f"{BUDGETS}/{budget['id']}",
        {
            "amount": 800,
            "cycleId": None,
            "category": "overhead",
            "periodStart": "2026-04-01",
            "periodEnd": "2026-04-30",
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["amount"] == 800
    assert updated.data["cycleId"] is None
    assert updated.data["category"] == "overhead"
    assert updated.data["periodStart"] == "2026-04-01"
    assert updated.data["periodEnd"] == "2026-04-30"

    detail = client.get(f"{BUDGETS}/{budget['id']}")
    assert detail.data == updated.data


def test_delete_budget_then_detail_returns_404(client):
    budget = create_budget(client, amount=100)

    deleted = client.delete(f"{BUDGETS}/{budget['id']}")
    assert deleted.status_code == 204
    assert client.get(f"{BUDGETS}/{budget['id']}").status_code == 404
    assert client.get(BUDGETS).data == []


def test_anonymous_budget_requests_return_401(anon):
    assert anon.get(BUDGETS).status_code == 401
    assert (
        anon.post(BUDGETS, {"amount": 100}, format="json").status_code
        == 401
    )
