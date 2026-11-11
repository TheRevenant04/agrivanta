import pytest
from rest_framework.test import APIClient

from api import reporting
from api.profitability import ProfitabilityError

from api.tests.conftest import register

REPORTS = "/api/reports/profitability"


def _post(client, path, payload):
    response = client.post(path, payload, format="json")
    assert response.status_code == 201, response.data
    return response.data


def _second_user(email="other@agrivanta.test"):
    client = APIClient()
    response = register(client, email=email)
    assert response.status_code == 201, response.data
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {response.data['token']}"
    )
    return client


def _build_farm_data(client, suffix):
    field = _post(
        client, "/api/fields", {"name": f"Field {suffix}", "area": "10"}
    )
    crop = _post(client, "/api/crops", {"name": f"Crop {suffix}"})
    variety = _post(
        client,
        "/api/varieties",
        {"cropId": crop["id"], "name": f"Variety {suffix}"},
    )
    unit = _post(
        client,
        "/api/units",
        {"name": f"unit-{suffix}", "baseMeasure": "mass"},
    )
    return {
        "field": field,
        "crop": crop,
        "variety": variety,
        "unit": unit,
    }


def _create_cycle(client, field, crop, variety, start, end=None):
    payload = {
        "fieldId": field["id"],
        "cropId": crop["id"],
        "varietyId": variety["id"],
        "cycleType": "annual",
        "startDate": start,
    }
    if end is not None:
        payload["endDate"] = end
    return _post(client, "/api/crop-cycles", payload)


def _add_harvest(client, cycle, unit, quantity, date):
    return _post(
        client,
        "/api/harvests",
        {
            "cycleId": cycle["id"],
            "quantity": quantity,
            "unitId": unit["id"],
            "date": date,
        },
    )


def _sell(client, harvest, customer, quantity, unit_price, date):
    return _post(
        client,
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest["id"],
            "quantity": quantity,
            "unitPrice": unit_price,
            "date": date,
        },
    )


def _add_expense(client, category, amount, date, cycle=None, post=False):
    payload = {"category": category, "amount": amount, "date": date}
    if cycle is not None:
        payload["cycleId"] = cycle["id"]
    created = _post(client, "/api/expenses", payload)
    if post:
        response = client.post(f"/api/expenses/{created['id']}/post")
        assert response.status_code == 200, response.data
    return created


def _create_season(client, name, start, end):
    return _post(
        client,
        "/api/seasons",
        {"name": name, "startDate": start, "endDate": end},
    )


@pytest.fixture
def kpi(client, setup):
    base = setup()
    field_a = base["field"]
    field_b = _post(
        client, "/api/fields", {"name": "South 20", "area": "8"}
    )
    crop = base["crop"]
    variety = base["variety"]
    unit = base["unit"]

    cycle_1 = _create_cycle(
        client, field_a, crop, variety, "2026-01-10", "2026-06-30"
    )
    cycle_2 = _create_cycle(
        client, field_a, crop, variety, "2026-07-01", "2026-12-31"
    )
    cycle_3 = _create_cycle(
        client, field_b, crop, variety, "2026-10-01"
    )

    customer = client.get("/api/customers").data[0]
    harvest_1 = _add_harvest(
        client, cycle_1, unit, "100", "2026-06-01"
    )
    _sell(client, harvest_1, customer, "100", "5", "2026-06-10")
    harvest_2 = _add_harvest(
        client, cycle_2, unit, "200", "2026-11-01"
    )
    _sell(client, harvest_2, customer, "200", "2", "2026-11-10")

    _add_expense(
        client, "inputs", "120", "2026-02-01", cycle_1, post=True
    )
    _add_expense(
        client, "labour", "80", "2026-03-01", cycle_1, post=True
    )
    _add_expense(
        client, "overhead", "50", "2026-03-02", cycle_1, post=True
    )
    # Draft costs must never reach the aggregation.
    _add_expense(client, "inputs", "1000", "2026-03-03", cycle_1)
    _add_expense(
        client, "equipment", "150", "2026-08-01", cycle_2, post=True
    )
    _add_expense(
        client, "overhead", "25", "2026-08-02", cycle_2, post=True
    )
    _add_expense(
        client, "inputs", "300", "2026-10-05", cycle_3, post=True
    )
    _add_expense(
        client, "overhead", "40", "2026-10-06", cycle_3, post=True
    )
    # Farm-level costs (no cycle) stay outside every cycle group.
    _add_expense(client, "other", "999", "2026-10-07", post=True)

    season_1 = _create_season(
        client, "Spring 2026", "2026-01-01", "2026-04-30"
    )
    season_2 = _create_season(
        client, "Long Season", "2026-03-01", "2026-09-30"
    )
    season_3 = _create_season(
        client, "Winter 2026/27", "2026-10-01", "2027-03-31"
    )

    return {
        "farm": client.get("/api/farm").data,
        "fieldA": field_a,
        "fieldB": field_b,
        "cycles": {
            "cycle_1": cycle_1,
            "cycle_2": cycle_2,
            "cycle_3": cycle_3,
        },
        "seasons": {
            "season_1": season_1,
            "season_2": season_2,
            "season_3": season_3,
        },
        "unit": unit,
    }


def _rows_by_cycle(client):
    response = client.get(REPORTS)
    assert response.status_code == 200, response.data
    return {row["cycleId"]: row for row in response.data}


def test_crop_cycle_grouping_matches_hand_computed_figures(client, kpi):
    rows = _rows_by_cycle(client)

    cycle_1 = rows[kpi["cycles"]["cycle_1"]["id"]]
    assert cycle_1["fieldName"] == "North 40"
    assert cycle_1["cropName"] == "Wheat"
    assert cycle_1["startDate"] == "2026-01-10"
    assert cycle_1["endDate"] == "2026-06-30"
    assert cycle_1["revenue"] == 500.0
    assert cycle_1["directCosts"] == 200.0
    assert cycle_1["allocatedOverheads"] == 50.0
    assert cycle_1["operatingSurplus"] == 300.0
    assert cycle_1["resultAfterAllocatedOverheads"] == 250.0

    cycle_2 = rows[kpi["cycles"]["cycle_2"]["id"]]
    assert cycle_2["revenue"] == 400.0
    assert cycle_2["directCosts"] == 150.0
    assert cycle_2["allocatedOverheads"] == 25.0
    assert cycle_2["operatingSurplus"] == 250.0
    assert cycle_2["resultAfterAllocatedOverheads"] == 225.0


def test_operating_surplus_and_result_after_overheads_are_separate(
    client, kpi
):
    rows = _rows_by_cycle(client)
    cycle_1 = rows[kpi["cycles"]["cycle_1"]["id"]]

    assert "operatingSurplus" in cycle_1
    assert "resultAfterAllocatedOverheads" in cycle_1
    assert cycle_1["operatingSurplus"] == 300.0
    assert cycle_1["resultAfterAllocatedOverheads"] == 250.0
    assert (
        cycle_1["operatingSurplus"]
        != cycle_1["resultAfterAllocatedOverheads"]
    )


def test_draft_expenses_excluded_and_posted_expenses_included(
    client, kpi
):
    rows = _rows_by_cycle(client)
    cycle_1 = rows[kpi["cycles"]["cycle_1"]["id"]]

    # Posted 120 + 80 = 200; the 1000 draft is ignored.
    assert cycle_1["directCosts"] == 200.0
    assert cycle_1["allocatedOverheads"] == 50.0


def test_field_grouping_totals_equal_sum_of_its_cycles(client, kpi):
    response = client.get(REPORTS, {"group_by": "field"})
    assert response.status_code == 200, response.data
    fields = {item["fieldId"]: item for item in response.data}

    field_a = fields[kpi["fieldA"]["id"]]
    assert field_a["fieldName"] == "North 40"
    assert field_a["cycleCount"] == 2
    assert [cycle["cycleId"] for cycle in field_a["cycles"]] == [
        kpi["cycles"]["cycle_1"]["id"],
        kpi["cycles"]["cycle_2"]["id"],
    ]
    assert field_a["revenue"] == 900.0
    assert field_a["directCosts"] == 350.0
    assert field_a["allocatedOverheads"] == 75.0
    assert field_a["operatingSurplus"] == 550.0
    assert field_a["resultAfterAllocatedOverheads"] == 475.0

    field_b = fields[kpi["fieldB"]["id"]]
    assert field_b["cycleCount"] == 1
    assert field_b["revenue"] == 0.0
    assert field_b["directCosts"] == 300.0
    assert field_b["operatingSurplus"] == -300.0


def test_season_grouping_lists_overlapping_cycles_with_identical_figures(
    client, kpi
):
    response = client.get(REPORTS, {"group_by": "season"})
    assert response.status_code == 200, response.data
    seasons = {item["seasonId"]: item for item in response.data}

    spring = seasons[kpi["seasons"]["season_1"]["id"]]
    assert spring["name"] == "Spring 2026"
    assert spring["startDate"] == "2026-01-01"
    assert spring["endDate"] == "2026-04-30"
    assert [cycle["cycleId"] for cycle in spring["cycles"]] == [
        kpi["cycles"]["cycle_1"]["id"]
    ]

    long_season = seasons[kpi["seasons"]["season_2"]["id"]]
    winter = seasons[kpi["seasons"]["season_3"]["id"]]
    cycle_2_id = kpi["cycles"]["cycle_2"]["id"]
    in_long = next(
        cycle
        for cycle in long_season["cycles"]
        if cycle["cycleId"] == cycle_2_id
    )
    in_winter = next(
        cycle
        for cycle in winter["cycles"]
        if cycle["cycleId"] == cycle_2_id
    )
    assert in_long == in_winter
    assert in_long["revenue"] == 400.0
    assert in_long["operatingSurplus"] == 250.0
    assert in_long["resultAfterAllocatedOverheads"] == 225.0

    # Long Season overlaps cycle 1 and cycle 2.
    assert long_season["revenue"] == 900.0
    assert long_season["directCosts"] == 350.0
    assert long_season["allocatedOverheads"] == 75.0
    assert long_season["resultAfterAllocatedOverheads"] == 475.0
    # Winter overlaps cycle 2 and cycle 3.
    assert winter["revenue"] == 400.0
    assert winter["directCosts"] == 450.0
    assert winter["allocatedOverheads"] == 65.0
    assert winter["resultAfterAllocatedOverheads"] == -115.0


def test_farm_grouping_equals_sum_of_all_cycles(client, kpi):
    response = client.get(REPORTS, {"group_by": "farm"})
    assert response.status_code == 200, response.data
    assert len(response.data) == 1
    farm = response.data[0]

    assert farm["farmId"] == kpi["farm"]["id"]
    assert farm["farmName"] == kpi["farm"]["name"]
    assert farm["cycleCount"] == 3
    assert [cycle["cycleId"] for cycle in farm["cycles"]] == [
        kpi["cycles"]["cycle_1"]["id"],
        kpi["cycles"]["cycle_2"]["id"],
        kpi["cycles"]["cycle_3"]["id"],
    ]
    assert farm["revenue"] == 900.0
    assert farm["directCosts"] == 650.0
    assert farm["allocatedOverheads"] == 115.0
    assert farm["operatingSurplus"] == 250.0
    assert farm["resultAfterAllocatedOverheads"] == 135.0

    cycles = client.get(REPORTS).data
    assert farm["revenue"] == sum(row["revenue"] for row in cycles)
    assert farm["directCosts"] == sum(
        row["directCosts"] for row in cycles
    )
    assert farm["allocatedOverheads"] == sum(
        row["allocatedOverheads"] for row in cycles
    )
    assert farm["operatingSurplus"] == sum(
        row["operatingSurplus"] for row in cycles
    )
    assert farm["resultAfterAllocatedOverheads"] == sum(
        row["resultAfterAllocatedOverheads"] for row in cycles
    )


def test_anonymous_request_returns_401(anon):
    assert anon.get(REPORTS).status_code == 401


def test_farm_isolation_and_foreign_farm_query_returns_404(client, kpi):
    other_client = _second_user()
    other = _build_farm_data(other_client, "other")
    other_cycle = _create_cycle(
        other_client, other["field"], other["crop"], other["variety"],
        "2026-01-01",
    )
    _add_expense(
        other_client, "inputs", "50", "2026-01-02", other_cycle,
        post=True,
    )

    other_rows = other_client.get(REPORTS).data
    assert [row["cycleId"] for row in other_rows] == [other_cycle["id"]]
    assert other_rows[0]["directCosts"] == 50.0

    own_ids = {row["cycleId"] for row in client.get(REPORTS).data}
    assert own_ids == {
        kpi["cycles"]["cycle_1"]["id"],
        kpi["cycles"]["cycle_2"]["id"],
        kpi["cycles"]["cycle_3"]["id"],
    }

    farm_a_id = kpi["farm"]["id"]
    assert (
        other_client.get(REPORTS, {"farm": farm_a_id}).status_code == 404
    )
    assert (
        other_client.get(REPORTS, {"farmId": farm_a_id}).status_code
        == 404
    )
    assert (
        other_client.get(
            REPORTS, {"farm": "00000000-0000-0000-0000-000000000000"}
        ).status_code
        == 404
    )
    assert client.get(REPORTS, {"farm": farm_a_id}).status_code == 200


def test_unsupported_grouping_returns_400_listing_valid_values(client, kpi):
    response = client.get(REPORTS, {"group_by": "planet"})
    assert response.status_code == 400
    message = response.data["detail"]
    for grouping in ("crop_cycle", "field", "season", "farm"):
        assert grouping in message

    # Grouping names are trimmed and case-insensitive.
    assert (
        client.get(REPORTS, {"group_by": " FIELD "}).status_code == 200
    )


def test_farm_with_no_cycles_returns_200_and_empty_list(client):
    assert client.get(REPORTS).status_code == 200
    assert client.get(REPORTS).data == []
    for grouping in ("crop_cycle", "field", "season", "farm"):
        response = client.get(REPORTS, {"group_by": grouping})
        assert response.status_code == 200
        assert response.data == []


def test_cycle_with_costs_but_no_sales_is_present(client, kpi):
    rows = _rows_by_cycle(client)
    cycle_3 = rows[kpi["cycles"]["cycle_3"]["id"]]

    assert cycle_3["revenue"] == 0.0
    assert cycle_3["directCosts"] == 300.0
    assert cycle_3["allocatedOverheads"] == 40.0
    assert cycle_3["operatingSurplus"] == -300.0
    assert cycle_3["resultAfterAllocatedOverheads"] == -340.0


def test_calculation_error_becomes_400_naming_the_field(
    client, kpi, monkeypatch
):
    def raise_error(_data):
        raise ProfitabilityError("Missing required field: revenue")

    monkeypatch.setattr(
        reporting, "calculate_crop_cycle_profitability", raise_error
    )

    response = client.get(REPORTS)
    assert response.status_code == 400
    assert response.data["field"] == "revenue"
    assert "revenue" in response.data["detail"]


def test_endpoint_is_read_only(client, kpi):
    assert client.post(REPORTS, {}, format="json").status_code == 405
    assert client.put(REPORTS, {}, format="json").status_code == 405
    assert client.delete(REPORTS).status_code == 405


def test_expense_cycle_attribution_is_optional_and_validated(client, kpi):
    cycle_1 = kpi["cycles"]["cycle_1"]

    attributed = _add_expense(
        client, "inputs", "10", "2026-01-05", cycle_1
    )
    assert attributed["cycleId"] == cycle_1["id"]

    unassigned = _post(
        client,
        "/api/expenses",
        {"category": "inputs", "amount": "10", "date": "2026-01-06"},
    )
    assert unassigned["cycleId"] is None

    updated = client.put(
        f"/api/expenses/{unassigned['id']}",
        {
            "category": "inputs",
            "amount": "12",
            "date": "2026-01-06",
            "cycleId": cycle_1["id"],
        },
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.data["cycleId"] == cycle_1["id"]

    missing = client.post(
        "/api/expenses",
        {
            "category": "inputs",
            "amount": "10",
            "date": "2026-01-07",
            "cycleId": "00000000-0000-0000-0000-000000000000",
        },
        format="json",
    )
    assert missing.status_code == 404
    assert missing.data["field"] == "cycleId"

    other_client = _second_user()
    other = _build_farm_data(other_client, "cycle-owner")
    other_cycle = _create_cycle(
        other_client, other["field"], other["crop"], other["variety"],
        "2026-01-01",
    )
    foreign = client.post(
        "/api/expenses",
        {
            "category": "inputs",
            "amount": "10",
            "date": "2026-01-08",
            "cycleId": other_cycle["id"],
        },
        format="json",
    )
    assert foreign.status_code == 404
    assert foreign.data["field"] == "cycleId"
