import csv
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO

import pytest
from openpyxl import load_workbook

from api.models import (
    Activity,
    ActivityType,
    Crop,
    CropCycle,
    Farm,
    Field,
    LabourRecord,
    User,
    Worker,
)

EXPORT = "/api/reports/labour-usage/export"
REPORT = "/api/reports/labour-usage"
PROFITABILITY_EXPORT = "/api/reports/profitability/export"
REPORT_PATHS = {
    "profitability": "/api/reports/profitability",
    "budget-vs-actual": "/api/reports/budget-vs-actual",
    "activity-status": "/api/reports/activity-status",
    "inventory": "/api/reports/inventory",
    "labour-usage": REPORT,
    "equipment-usage": "/api/reports/equipment-usage",
    "dashboard": "/api/dashboard",
}


def _activity(farm, cycle, name):
    activity_type = ActivityType.objects.create(
        farm=farm,
        name=f"Plant {name}",
        category="planting",
    )
    return Activity.objects.create(
        farm=farm,
        cycle=cycle,
        type=activity_type,
        planned_date=date(2026, 3, 10),
        status="planned",
    )


def _labour_record(farm, worker, activity, when):
    return LabourRecord.objects.create(
        farm=farm,
        worker=worker,
        activity=activity,
        hours=Decimal("2.5"),
        hourly_cost=Decimal("12.50"),
        date=when,
    )


def _csv_rows(response):
    return list(csv.reader(StringIO(response.content.decode("utf-8"))))


def _spreadsheet_rows(response, sheet="Labour Usage"):
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    return workbook, list(workbook[sheet].values)


def test_labour_report_exports_match_filtered_payload_and_preserve_rows(
    client, cycle
):
    first = cycle()
    first_cycle = CropCycle.objects.get(pk=first["cycle"]["id"])
    farm = Farm.objects.get()
    second_field = Field.objects.create(
        farm=farm,
        name="Second field",
        area=Decimal("3"),
    )
    second_cycle = CropCycle.objects.create(
        farm=farm,
        field=second_field,
        crop=first_cycle.crop,
        variety=first_cycle.variety,
        cycle_type="annual",
        start_date=date(2026, 1, 1),
    )
    march_activity = _activity(farm, first_cycle, "March")
    april_activity = _activity(farm, first_cycle, "April")
    second_cycle_activity = _activity(farm, second_cycle, "Second cycle")

    workers = [
        Worker.objects.create(
            farm=farm,
            name="Café Worker" if index == 0 else f"Worker {index:02}",
        )
        for index in range(45)
    ]
    for worker in workers:
        _labour_record(
            farm, worker, march_activity, date(2026, 3, 15)
        )
    april_worker = Worker.objects.create(farm=farm, name="April Worker")
    _labour_record(
        farm, april_worker, april_activity, date(2026, 4, 15)
    )
    second_cycle_worker = Worker.objects.create(
        farm=farm, name="Other Cycle Worker"
    )
    _labour_record(
        farm,
        second_cycle_worker,
        second_cycle_activity,
        date(2026, 3, 15),
    )

    before = list(
        LabourRecord.objects.order_by("id").values_list(
            "id", "farm_id", "worker_id", "activity_id", "hours", "date"
        )
    )
    params = {
        "exportFormat": "csv",
        "cycleId": str(first_cycle.id),
        "startDate": "2026-03-01",
        "endDate": "2026-03-31",
    }
    expected = client.get(
        REPORT,
        {
            key: value
            for key, value in params.items()
            if key != "exportFormat"
        },
    )
    assert expected.status_code == 200, expected.data

    response = client.get(EXPORT, params)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"] == (
        'attachment; filename="agrivanta-labour-usage.csv"'
    )
    rows = _csv_rows(response)
    headers = list(expected.data["rows"][0])
    assert rows[0] == headers
    assert len(rows[1 : 1 + len(expected.data["rows"])]) == 45
    assert "Café Worker" in response.content.decode("utf-8")
    for values, expected_row in zip(
        rows[1 : 1 + len(expected.data["rows"])],
        expected.data["rows"],
        strict=True,
    ):
        assert values == [
            "" if expected_row[key] is None else str(expected_row[key])
            for key in headers
        ]

    xlsx_params = {**params, "exportFormat": "xlsx"}
    spreadsheet = client.get(EXPORT, xlsx_params)
    assert spreadsheet.status_code == 200
    assert spreadsheet["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert spreadsheet["Content-Disposition"] == (
        'attachment; filename="agrivanta-labour-usage.xlsx"'
    )
    workbook, sheet_rows = _spreadsheet_rows(spreadsheet)
    assert workbook.sheetnames == ["Labour Usage", "Summary"]
    assert list(sheet_rows[0]) == headers
    assert len(sheet_rows) == 46
    assert list(sheet_rows[1]) == list(expected.data["rows"][0].values())
    assert sheet_rows[1][2] == "Café Worker"
    workbook.close()

    unfiltered = client.get(EXPORT, {"exportFormat": "csv"})
    assert len(_csv_rows(unfiltered)[1 : 1 + 47]) == 47
    assert list(
        LabourRecord.objects.order_by("id").values_list(
            "id", "farm_id", "worker_id", "activity_id", "hours", "date"
        )
    ) == before


@pytest.mark.parametrize("file_format", ["csv", "xlsx"])
def test_empty_profitability_export_has_headers_and_valid_file(
    client, file_format
):
    response = client.get(
        PROFITABILITY_EXPORT,
        {"exportFormat": file_format},
    )
    assert response.status_code == 200, response.content
    headers = [
        "cycleId",
        "fieldId",
        "fieldName",
        "cropId",
        "cropName",
        "startDate",
        "endDate",
        "revenue",
        "directCosts",
        "allocatedOverheads",
        "operatingSurplus",
        "resultAfterAllocatedOverheads",
    ]
    if file_format == "csv":
        rows = _csv_rows(response)
        assert rows == [headers]
        assert response["Content-Type"] == "text/csv; charset=utf-8"
    else:
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        assert workbook.sheetnames == ["Profitability"]
        assert list(workbook["Profitability"].values) == [tuple(headers)]
        workbook.close()


@pytest.mark.parametrize("report_name", REPORT_PATHS)
def test_export_service_supports_existing_report_payloads(client, report_name):
    baseline = client.get(REPORT_PATHS[report_name])
    assert baseline.status_code == 200, baseline.data

    csv_response = client.get(
        f"/api/reports/{report_name}/export",
        {"exportFormat": "csv"},
    )
    xlsx_response = client.get(
        f"/api/reports/{report_name}/export",
        {"exportFormat": "xlsx"},
    )

    assert csv_response.status_code == 200, csv_response.content
    assert _csv_rows(csv_response)
    assert xlsx_response.status_code == 200, xlsx_response.content
    workbook = load_workbook(BytesIO(xlsx_response.content), read_only=True)
    assert workbook.sheetnames
    assert all(workbook[name].max_row >= 1 for name in workbook.sheetnames)
    workbook.close()


def test_export_requires_authentication_and_valid_format(anon, client):
    assert anon.get(EXPORT, {"exportFormat": "csv"}).status_code == 401
    assert client.get(EXPORT).status_code == 400
    invalid = client.get(EXPORT, {"exportFormat": "pdf"})
    assert invalid.status_code == 400
    assert invalid.data["field"] == "exportFormat"
    unknown = client.get(
        "/api/reports/unknown/export", {"exportFormat": "csv"}
    )
    assert unknown.status_code == 404


def test_export_uses_only_the_authenticated_farm(client, cycle):
    built = cycle()
    local_cycle = CropCycle.objects.get(pk=built["cycle"]["id"])
    farm = Farm.objects.get()
    local_activity = _activity(farm, local_cycle, "Local")
    local_worker = Worker.objects.create(farm=farm, name="Local worker")
    _labour_record(farm, local_worker, local_activity, date(2026, 3, 15))

    foreign_owner = User.objects.create_user(
        email="foreign-export@agrivanta.test",
        password="ForeignExport#42",
    )
    foreign_farm = Farm.objects.create(
        owner=foreign_owner,
        name="Foreign farm",
        reporting_currency="USD",
    )
    foreign_field = Field.objects.create(
        farm=foreign_farm,
        name="Foreign field",
        area=Decimal("1"),
    )
    foreign_crop = Crop.objects.create(
        farm=foreign_farm,
        name="Foreign crop",
    )
    foreign_cycle = CropCycle.objects.create(
        farm=foreign_farm,
        field=foreign_field,
        crop=foreign_crop,
        cycle_type="annual",
        start_date=date(2026, 1, 1),
    )
    foreign_activity = _activity(foreign_farm, foreign_cycle, "Foreign")
    foreign_worker = Worker.objects.create(
        farm=foreign_farm, name="Foreign worker"
    )
    _labour_record(
        foreign_farm,
        foreign_worker,
        foreign_activity,
        date(2026, 3, 15),
    )

    response = client.get(EXPORT, {"exportFormat": "csv"})
    assert response.status_code == 200
    rows = _csv_rows(response)
    assert len(rows[1]) == 5
    assert len(rows) > 1
    assert all("Foreign worker" not in row for row in rows)
