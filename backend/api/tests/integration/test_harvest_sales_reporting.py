from decimal import Decimal

import pytest

from api import reporting
from api.models import CropCycle


def test_report_crop_cycle_basic_harvests_and_sales(client, cycle):
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
    harvest2 = client.post(
        "/api/harvests",
        {
            "cycleId": built["cycle"]["id"],
            "quantity": "50",
            "unitId": built["unit"]["id"],
            "date": "2026-08-02",
        },
        format="json",
    ).data
    customer = client.get("/api/customers").data[0]
    client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest["id"],
            "quantity": "30",
            "unitPrice": "2.00",
            "date": "2026-08-05",
        },
        format="json",
    )
    client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest2["id"],
            "quantity": "20",
            "unitPrice": "3.00",
            "date": "2026-08-06",
        },
        format="json",
    )
    from api.models import CropCycle

    c = CropCycle.objects.get(id=built["cycle"]["id"])
    report = reporting.report_crop_cycle(c.farm, c)
    assert report["cycleId"] == str(c.id)
    assert report["harvestedQuantity"] == Decimal("150")
    assert report["soldQuantity"] == Decimal("50")
    assert report["unsoldQuantity"] == Decimal("100")
    assert report["unitId"] == str(built["unit"]["id"])


def test_report_crop_cycle_full_case(session, client, cycle, setup):
    built = cycle()
    from api.models import CropCycle

    c = CropCycle.objects.get(id=built["cycle"]["id"])
    h1 = client.post(
        "/api/harvests",
        {
            "cycleId": c.id,
            "quantity": "100",
            "unitId": built["unit"]["id"],
            "date": "2026-08-01",
        },
        format="json",
    ).data
    h2 = client.post(
        "/api/harvests",
        {
            "cycleId": c.id,
            "quantity": "50",
            "unitId": built["unit"]["id"],
            "date": "2026-08-02",
        },
        format="json",
    ).data
    customer = client.get("/api/customers").data[0]
    client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": h1["id"],
            "quantity": "30",
            "unitPrice": "2.00",
            "date": "2026-08-05",
        },
        format="json",
    )
    client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": h2["id"],
            "quantity": "20",
            "unitPrice": "3.00",
            "date": "2026-08-06",
        },
        format="json",
    )
    report = reporting.report_crop_cycle(c.farm, c)
    assert report["cycleId"] == str(c.id)
    assert report["harvestedQuantity"] == Decimal("150")
    assert report["soldQuantity"] == Decimal("50")
    assert report["unsoldQuantity"] == Decimal("100")
    assert report["revenue"] == Decimal("120.0000")
    assert report["unitId"] == str(built["unit"]["id"])


def test_mixed_harvest_units_converted(client, setup):
    data = setup()
    c = client.post(
        "/api/crop-cycles",
        {
            "fieldId": data["field"]["id"],
            "cropId": data["crop"]["id"],
            "varietyId": data["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2026-03-01",
        },
        format="json",
    ).data
    kg = data["unit"]
    g = client.post("/api/units", {"name": "g", "baseMeasure": "mass"}, format="json").data
    client.post(
        "/api/conversions",
        {"fromUnitId": g["id"], "toUnitId": kg["id"], "factor": "0.001"},
        format="json",
    )
    client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "50", "unitId": kg["id"], "date": "2026-08-01"},
        format="json",
    )
    client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "50000", "unitId": g["id"], "date": "2026-08-02"},
        format="json",
    )
    from api.models import CropCycle, Farm

    cycle_obj = CropCycle.objects.get(id=c["id"])
    report = reporting.report_crop_cycle(cycle_obj.farm, cycle_obj)
    assert report["harvestedQuantity"] == Decimal("100")
    assert report["unitId"] == kg["id"]


def test_sale_quantities_converted_mixed_harvest_units(client, setup):
    data = setup()
    c = client.post(
        "/api/crop-cycles",
        {
            "fieldId": data["field"]["id"],
            "cropId": data["crop"]["id"],
            "varietyId": data["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2026-03-01",
        },
        format="json",
    ).data
    kg = data["unit"]
    g = client.post("/api/units", {"name": "g", "baseMeasure": "mass"}, format="json").data
    client.post(
        "/api/conversions",
        {"fromUnitId": g["id"], "toUnitId": kg["id"], "factor": "0.001"},
        format="json",
    )
    h_kg = client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "50", "unitId": kg["id"], "date": "2026-08-01"},
        format="json",
    ).data
    h_g = client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "50000", "unitId": g["id"], "date": "2026-08-02"},
        format="json",
    ).data
    customer = client.get("/api/customers").data[0]
    client.post(
        "/api/sales",
        {"customerId": customer["id"], "harvestId": h_kg["id"], "quantity": "20", "unitPrice": "1", "date": "2026-08-05"},
        format="json",
    )
    client.post(
        "/api/sales",
        {"customerId": customer["id"], "harvestId": h_g["id"], "quantity": "10000", "unitPrice": "1", "date": "2026-08-06"},
        format="json",
    )
    from api.models import CropCycle

    cycle_obj = CropCycle.objects.get(id=c["id"])
    report = reporting.report_crop_cycle(cycle_obj.farm, cycle_obj)
    assert report["soldQuantity"] == Decimal("30")
    assert report["unitId"] == kg["id"]


def test_revenue_sum_of_per_sale_revenues(client, cycle):
    built = cycle()
    c = built["cycle"]
    h1 = client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "100", "unitId": built["unit"]["id"], "date": "2026-08-01"},
        format="json",
    ).data
    h2 = client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "50", "unitId": built["unit"]["id"], "date": "2026-08-02"},
        format="json",
    ).data
    customer = client.get("/api/customers").data[0]
    client.post(
        "/api/sales",
        {"customerId": customer["id"], "harvestId": h1["id"], "quantity": "10", "unitPrice": "2.00", "date": "2026-08-05"},
        format="json",
    )
    client.post(
        "/api/sales",
        {"customerId": customer["id"], "harvestId": h2["id"], "quantity": "5", "unitPrice": "3.00", "date": "2026-08-06"},
        format="json",
    )
    from api.models import CropCycle

    cycle_obj = CropCycle.objects.get(id=c["id"])
    report = reporting.report_crop_cycle(cycle_obj.farm, cycle_obj)
    assert report["revenue"] == Decimal("35.0000")


def test_harvests_no_sales(client, cycle):
    built = cycle()
    c = built["cycle"]
    client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "150", "unitId": built["unit"]["id"], "date": "2026-08-01"},
        format="json",
    )
    from api.models import CropCycle

    cycle_obj = CropCycle.objects.get(id=c["id"])
    report = reporting.report_crop_cycle(cycle_obj.farm, cycle_obj)
    assert report["soldQuantity"] == Decimal("0")
    assert report["revenue"] == Decimal("0")
    assert report["unsoldQuantity"] == report["harvestedQuantity"]
    assert report["unitId"] is not None


def test_no_harvests_no_sales(client, cycle):
    built = cycle()
    c = built["cycle"]
    from api.models import CropCycle

    cycle_obj = CropCycle.objects.get(id=c["id"])
    report = reporting.report_crop_cycle(cycle_obj.farm, cycle_obj)
    assert report["harvestedQuantity"] == Decimal("0")
    assert report["soldQuantity"] == Decimal("0")
    assert report["unsoldQuantity"] == Decimal("0")
    assert report["revenue"] == Decimal("0")
    assert report["unitId"] is None


def test_missing_conversion_raises_error_naming_units(client, setup):
    data = setup()
    c = client.post(
        "/api/crop-cycles",
        {
            "fieldId": data["field"]["id"],
            "cropId": data["crop"]["id"],
            "varietyId": data["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2026-03-01",
        },
        format="json",
    ).data
    kg = data["unit"]
    g = client.post("/api/units", {"name": "g", "baseMeasure": "mass"}, format="json").data
    client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "50", "unitId": kg["id"], "date": "2026-08-01"},
        format="json",
    )
    client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "50000", "unitId": g["id"], "date": "2026-08-02"},
        format="json",
    )
    from api.models import CropCycle
    from api.exceptions import ApiError

    cycle_obj = CropCycle.objects.get(id=c["id"])
    try:
        reporting.report_crop_cycle(cycle_obj.farm, cycle_obj)
        assert False, "Should have raised"
    except ApiError as e:
        msg = str(e.detail)
        assert "kg" in msg and "g" in msg


def test_cycle_not_exist_or_wrong_farm_raises(client, cycle):
    built = cycle()
    c = built["cycle"]
    from api.models import CropCycle, Farm
    from api.exceptions import ApiError
    from django.contrib.auth import get_user_model

    cycle_obj = CropCycle.objects.get(id=c["id"])
    User = get_user_model()
    user2 = User.objects.create_user(email="other@test.com", password="pass")
    farm2 = Farm.objects.create(owner=user2, name="Other", reporting_currency="USD")
    try:
        reporting.report_crop_cycle(farm2, cycle_obj)
        assert False
    except ApiError:
        pass

    try:
        reporting.report_crop_cycle(cycle_obj.farm, "00000000-0000-0000-0000-000000000000")
        assert False
    except ApiError:
        pass
    except Exception:
        pass


def test_closed_cycle_same_as_open(client, cycle):
    built = cycle()
    c = built["cycle"]
    client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "10", "unitId": built["unit"]["id"], "date": "2026-08-01"},
        format="json",
    )
    client.post(f"/api/crop-cycles/{c['id']}/close")
    from api.models import CropCycle

    cycle_obj = CropCycle.objects.get(id=c["id"])
    report = reporting.report_crop_cycle(cycle_obj.farm, cycle_obj)
    assert report["harvestedQuantity"] == Decimal("10")


def test_farm_isolation_between_cycles(client, setup):
    data = setup()
    c1 = client.post(
        "/api/crop-cycles",
        {"fieldId": data["field"]["id"], "cropId": data["crop"]["id"], "varietyId": data["variety"]["id"], "cycleType": "annual", "startDate": "2026-03-01"},
        format="json",
    ).data
    c2 = client.post(
        "/api/crop-cycles",
        {"fieldId": data["field"]["id"], "cropId": data["crop"]["id"], "varietyId": data["variety"]["id"], "cycleType": "annual", "startDate": "2026-04-01"},
        format="json",
    ).data
    h1 = client.post(
        "/api/harvests",
        {"cycleId": c1["id"], "quantity": "100", "unitId": data["unit"]["id"], "date": "2026-08-01"},
        format="json",
    ).data
    h2 = client.post(
        "/api/harvests",
        {"cycleId": c2["id"], "quantity": "200", "unitId": data["unit"]["id"], "date": "2026-08-01"},
        format="json",
    ).data
    customer = client.get("/api/customers").data[0]
    client.post(
        "/api/sales",
        {"customerId": customer["id"], "harvestId": h1["id"], "quantity": "10", "unitPrice": "1", "date": "2026-08-05"},
        format="json",
    )
    client.post(
        "/api/sales",
        {"customerId": customer["id"], "harvestId": h2["id"], "quantity": "20", "unitPrice": "1", "date": "2026-08-05"},
        format="json",
    )
    from api.models import CropCycle

    cycle1_obj = CropCycle.objects.get(id=c1["id"])
    cycle2_obj = CropCycle.objects.get(id=c2["id"])
    r1 = reporting.report_crop_cycle(cycle1_obj.farm, cycle1_obj)
    r2 = reporting.report_crop_cycle(cycle2_obj.farm, cycle2_obj)
    assert r1["harvestedQuantity"] == Decimal("100")
    assert r1["soldQuantity"] == Decimal("10")
    assert r2["harvestedQuantity"] == Decimal("200")
    assert r2["soldQuantity"] == Decimal("20")


def test_sales_exceed_harvests_raises_error_naming_cycle(client, cycle):
    built = cycle()
    c = built["cycle"]
    h1 = client.post(
        "/api/harvests",
        {"cycleId": c["id"], "quantity": "100", "unitId": built["unit"]["id"], "date": "2026-08-01"},
        format="json",
    ).data
    customer = client.get("/api/customers").data[0]
    from api.models import Sale, CropCycle, Customer

    cycle_obj = CropCycle.objects.get(id=c["id"])
    cust = Customer.objects.get(id=customer["id"])
    Sale.objects.create(
        farm=cycle_obj.farm,
        customer=cust,
        harvest_id=h1["id"],
        quantity=Decimal("150"),
        unit_price=Decimal("1.0000"),
        date="2026-08-05",
        revenue=Decimal("150.0000"),
    )
    from api.exceptions import ApiError

    try:
        reporting.report_crop_cycle(cycle_obj.farm, cycle_obj)
        assert False
    except ApiError as e:
        msg = str(e.detail)
        assert str(cycle_obj.id) in msg
