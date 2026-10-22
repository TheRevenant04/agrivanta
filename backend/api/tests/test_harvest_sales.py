def test_harvest_can_be_created_and_filtered(client, cycle):
    built = cycle()

    created = client.post(
        "/api/harvests",
        {
            "cycleId": built["cycle"]["id"],
            "quantity": "500",
            "unitId": built["unit"]["id"],
            "date": "2026-08-01",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["quantity"] == 500
    assert created.data["unitId"] == built["unit"]["id"]

    filtered = client.get(
        f"/api/harvests?cycle={built['cycle']['id']}"
    )
    assert len(filtered.data) == 1

    refs = client.get("/api/harvests/cycles")
    assert refs.status_code == 200
    assert refs.data[0]["id"] == built["cycle"]["id"]


def test_closed_cycle_cannot_be_harvested(client, cycle):
    built = cycle()
    client.post(f"/api/crop-cycles/{built['cycle']['id']}/close")

    response = client.post(
        "/api/harvests",
        {
            "cycleId": built["cycle"]["id"],
            "quantity": "10",
            "unitId": built["unit"]["id"],
            "date": "2026-08-01",
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == "cycleId"


def test_harvest_validation(client, cycle):
    built = cycle()

    missing_cycle = client.post(
        "/api/harvests",
        {
            "quantity": "10",
            "unitId": built["unit"]["id"],
            "date": "2026-08-01",
        },
        format="json",
    )
    assert missing_cycle.status_code == 400
    assert missing_cycle.data["field"] == "cycleId"

    zero_quantity = client.post(
        "/api/harvests",
        {
            "cycleId": built["cycle"]["id"],
            "quantity": "0",
            "unitId": built["unit"]["id"],
            "date": "2026-08-01",
        },
        format="json",
    )
    assert zero_quantity.status_code == 400
    assert zero_quantity.data["field"] == "quantity"

    bad_date = client.post(
        "/api/harvests",
        {
            "cycleId": built["cycle"]["id"],
            "quantity": "10",
            "unitId": built["unit"]["id"],
            "date": "2026-13-01",
        },
        format="json",
    )
    assert bad_date.status_code == 400
    assert bad_date.data["field"] == "date"


def test_sales_cannot_exceed_harvested_quantity(client, cycle):
    built = cycle()
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

    first = client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest["id"],
            "quantity": "60",
            "unitPrice": "2.5",
            "date": "2026-08-05",
        },
        format="json",
    )
    assert first.status_code == 201
    assert first.data["revenue"] == 150

    over = client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest["id"],
            "quantity": "50",
            "unitPrice": "2.5",
            "date": "2026-08-06",
        },
        format="json",
    )
    assert over.status_code == 400
    assert over.data["field"] == "quantity"

    remaining = client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest["id"],
            "quantity": "40",
            "unitPrice": "2.5",
            "date": "2026-08-07",
        },
        format="json",
    )
    assert remaining.status_code == 201

    assert len(client.get("/api/sales").data) == 2


def test_sales_validate_links_and_amounts(client, cycle):
    built = cycle()
    harvest = client.post(
        "/api/harvests",
        {
            "cycleId": built["cycle"]["id"],
            "quantity": "20",
            "unitId": built["unit"]["id"],
            "date": "2026-08-01",
        },
        format="json",
    ).data
    customer = client.get("/api/customers").data[0]

    missing_customer = client.post(
        "/api/sales",
        {
            "harvestId": harvest["id"],
            "quantity": "1",
            "unitPrice": "1",
            "date": "2026-08-05",
        },
        format="json",
    )
    assert missing_customer.status_code == 400
    assert missing_customer.data["field"] == "customerId"

    bad_price = client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest["id"],
            "quantity": "1",
            "unitPrice": "0",
            "date": "2026-08-05",
        },
        format="json",
    )
    assert bad_price.status_code == 400
    assert bad_price.data["field"] == "unitPrice"

    payment = client.post(
        "/api/payments",
        {
            "type": "received",
            "amount": "2.5",
            "date": "2026-08-08",
            "linkedSaleId": "00000000-0000-0000-0000-000000000000",
        },
        format="json",
    )
    assert payment.status_code == 400
    assert payment.data["field"] == "linkedSaleId"


def test_seeded_customers_are_available(client):
    customers = client.get("/api/customers")
    assert customers.status_code == 200
    assert [row["name"] for row in customers.data] == [
        "Greenfield Grain Co.",
        "Harbour Mill",
    ]
