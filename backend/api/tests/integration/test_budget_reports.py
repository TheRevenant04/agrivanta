from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api import budget_reports
from api.budget_reports import _variance_percentage
from api.models import (
    AllocationRule,
    Budget,
    CropCycle,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Farm,
    User,
)

REPORT = "/api/reports/budget-vs-actual"


def _create_cycle(client, data, *, field_name, area):
    field = client.post(
        "/api/fields",
        {"name": field_name, "area": str(area)},
        format="json",
    )
    assert field.status_code == 201, field.data
    response = client.post(
        "/api/crop-cycles",
        {
            "fieldId": field.data["id"],
            "cropId": data["crop"]["id"],
            "varietyId": data["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2026-01-01",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return CropCycle.objects.get(pk=response.data["id"])


def _budget(client, amount, *, cycle=None, category=None):
    payload = {"amount": str(amount)}
    if cycle is not None:
        payload["cycleId"] = str(cycle.id)
    if category is not None:
        payload["category"] = category
    response = client.post("/api/budgets", payload, format="json")
    assert response.status_code == 201, response.data
    return response.data


def _expense(farm, amount, when, *, cycle=None, category, status=None):
    return Expense.objects.create(
        farm=farm,
        cycle=cycle,
        category=category,
        amount=Decimal(amount),
        date=date.fromisoformat(when),
        status=status or ExpenseStatus.POSTED,
    )


def _lines(response):
    return {
        row["budgetId"]: row
        for row in response.data["overall"] + response.data["categories"]
    }


def test_budget_report_requires_authentication_and_is_read_only(anon, client):
    assert anon.get(REPORT).status_code == 401

    for method in (client.post, client.put, client.patch, client.delete):
        assert method(REPORT, format="json").status_code == 405


def test_budget_report_calculates_direct_and_allocated_actuals(
    client, setup
):
    data = setup()
    first_cycle = _create_cycle(
        client, data, field_name="North field", area=1
    )
    farm = Farm.objects.get(owner__email="owner@agrivanta.test")
    second_cycle = _create_cycle(
        client, data, field_name="South field", area=3
    )

    _expense(
        farm,
        "50",
        "2026-03-01",
        cycle=first_cycle,
        category=ExpenseCategory.INPUTS,
    )
    _expense(
        farm,
        "20",
        "2026-03-02",
        cycle=first_cycle,
        category=ExpenseCategory.LABOUR,
    )
    _expense(
        farm,
        "40",
        "2026-03-03",
        cycle=second_cycle,
        category=ExpenseCategory.INPUTS,
    )
    _expense(
        farm,
        "999",
        "2026-03-04",
        cycle=first_cycle,
        category=ExpenseCategory.INPUTS,
        status=ExpenseStatus.DRAFT,
    )
    _expense(
        farm,
        "80",
        "2026-03-05",
        category=ExpenseCategory.OVERHEAD,
    )
    AllocationRule.objects.create(
        farm=farm,
        name="Allocate overhead by area",
        basis="per_hectare",
        active_from=date(2026, 1, 1),
    )

    first_overall = _budget(client, 80, cycle=first_cycle)
    second_overall = _budget(client, 120, cycle=second_cycle)
    inputs = _budget(
        client, 50, cycle=first_cycle, category=ExpenseCategory.INPUTS
    )
    labour = _budget(
        client, 25, cycle=first_cycle, category=ExpenseCategory.LABOUR
    )
    overhead = _budget(
        client, 10, cycle=first_cycle, category=ExpenseCategory.OVERHEAD
    )

    response = client.get(REPORT)

    assert response.status_code == 200, response.data
    assert len(response.data["overall"]) == 2
    assert len(response.data["categories"]) == 3
    lines = _lines(response)
    assert lines[first_overall["id"]]["actual"] == 90
    assert lines[first_overall["id"]]["variance"] == 10
    assert lines[first_overall["id"]]["variancePercentage"] == 12.5
    assert lines[second_overall["id"]]["actual"] == 100
    assert lines[second_overall["id"]]["variance"] == -20
    assert lines[second_overall["id"]]["variancePercentage"] == -16.67
    assert lines[inputs["id"]]["actual"] == 50
    assert lines[inputs["id"]]["variance"] == 0
    assert lines[inputs["id"]]["variancePercentage"] == 0
    assert lines[labour["id"]]["actual"] == 20
    assert lines[labour["id"]]["variance"] == -5
    assert lines[labour["id"]]["variancePercentage"] == -20
    assert lines[overhead["id"]]["actual"] == 20
    assert lines[overhead["id"]]["variance"] == 10
    assert lines[overhead["id"]]["variancePercentage"] == 100
    assert sum(
        lines[budget_id]["actual"]
        for budget_id in (inputs["id"], labour["id"], overhead["id"])
    ) == lines[first_overall["id"]]["actual"]


def test_budget_without_actuals_returns_zero_actual_and_valid_variance(
    client, cycle
):
    data = cycle()
    cycle_obj = CropCycle.objects.get(pk=data["cycle"]["id"])
    overall = _budget(client, 120, cycle=cycle_obj)
    category = _budget(
        client,
        50,
        cycle=cycle_obj,
        category=ExpenseCategory.INPUTS,
    )

    response = client.get(REPORT)

    assert response.status_code == 200, response.data
    lines = _lines(response)
    assert lines[overall["id"]]["actual"] == 0
    assert lines[overall["id"]]["variance"] == -120
    assert lines[overall["id"]]["variancePercentage"] == -100
    assert lines[category["id"]]["actual"] == 0


def test_zero_budget_line_has_division_safe_percentage(monkeypatch):
    assert _variance_percentage(Decimal(0), Decimal("12.50")) is None
    assert _variance_percentage(Decimal(0), Decimal(0)) is None
    budget = SimpleNamespace(
        id=uuid4(),
        cycle_id=None,
        cycle=None,
        category=None,
        amount=Decimal(0),
        period_start=None,
        period_end=None,
    )
    monkeypatch.setattr(
        budget_reports, "_actual_for_budget", lambda *args: Decimal("12.50")
    )

    line = budget_reports._budget_line(None, budget, None, None)

    assert line["budget"] == 0
    assert line["actual"] == 12.5
    assert line["variance"] == 12.5
    assert line["variancePercentage"] is None


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"budgetId": "not-a-uuid"}, "budgetId"),
        (
            {"budgetId": "00000000-0000-0000-0000-000000000000"},
            "budgetId",
        ),
        (
            {"cycleId": "00000000-0000-0000-0000-000000000000"},
            "cycleId",
        ),
        (
            {"periodId": "00000000-0000-0000-0000-000000000000"},
            "periodId",
        ),
        (
            {"startDate": "not-a-date", "endDate": "2026-03-31"},
            "startDate",
        ),
    ],
)
def test_budget_report_rejects_invalid_filters(client, params, field):
    response = client.get(REPORT, params)

    assert response.status_code == 400
    assert response.data["field"] == field


def test_budget_report_is_scoped_to_the_authenticated_farm(client):
    owner = User.objects.create_user(
        email="other-farm@agrivanta.test",
        password="OliveHarvest#42",
    )
    other_farm = Farm.objects.create(
        owner=owner, name="Other farm", reporting_currency="USD"
    )
    foreign_budget = Budget.objects.create(
        farm=other_farm,
        amount=Decimal("100"),
    )

    response = client.get(REPORT)

    assert response.status_code == 200, response.data
    assert response.data == {"overall": [], "categories": []}
    filtered = client.get(REPORT, {"budgetId": str(foreign_budget.id)})
    assert filtered.status_code == 400
    assert filtered.data["field"] == "budgetId"
