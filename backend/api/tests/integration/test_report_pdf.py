from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
from threading import Thread
from unittest.mock import Mock

import pytest
from pypdf import PdfReader

from api.models import (
    Activity,
    ActivityType,
    Crop,
    CropCycle,
    Farm,
    Field,
    LabourRecord,
    ReportingPeriod,
    User,
    Worker,
)
from api.pdf_chromium import render_chromium_pdf

EXPORT = "/api/reports/labour-usage/export"
REPORT = "/api/reports/labour-usage"


def pdf_text(response):
    assert response.status_code == 200, response.content
    assert response["Content-Type"] == "application/pdf"
    reader = PdfReader(BytesIO(response.content), strict=True)
    assert reader.pages
    return reader, "\n".join(page.extract_text() for page in reader.pages)


def add_record(farm, cycle, name, when):
    kind = ActivityType.objects.create(
        farm=farm, name=f"Plant {name}", category="planting"
    )
    activity = Activity.objects.create(
        farm=farm, cycle=cycle, type=kind, planned_date=when, status="planned"
    )
    worker = Worker.objects.create(farm=farm, name=name)
    LabourRecord.objects.create(
        farm=farm, worker=worker, activity=activity,
        hours=Decimal("2.5"), hourly_cost=Decimal("12.50"), date=when,
    )


def test_pdf_matches_filtered_report_and_paginates(client, cycle):
    built = cycle()
    farm = Farm.objects.get()
    farm.name = "Café & Farm"
    farm.save()
    local_cycle = CropCycle.objects.get(pk=built["cycle"]["id"])
    for index in range(25):
        add_record(farm, local_cycle, f"Worker {index:02}", date(2026, 3, 15))
    add_record(farm, local_cycle, "April worker", date(2026, 4, 15))
    other_field = Field.objects.create(farm=farm, name="Other", area=1)
    other_cycle = CropCycle.objects.create(
        farm=farm, field=other_field, crop=local_cycle.crop,
        cycle_type="annual", start_date=date(2026, 1, 1),
    )
    add_record(farm, other_cycle, "Other cycle", date(2026, 3, 15))
    filters = {
        "cycleId": str(local_cycle.id),
        "startDate": "2026-03-01",
        "endDate": "2026-03-31",
    }
    expected = client.get(REPORT, filters)
    assert expected.status_code == 200
    response = client.get(EXPORT, {**filters, "exportFormat": "pdf"})
    assert response["Content-Disposition"] == (
        'attachment; filename="agrivanta-labour-usage.pdf"'
    )
    reader, text = pdf_text(response)
    assert len(reader.pages) > 1
    assert "Café & Farm" in text
    assert "2026-03-01 to 2026-03-31" in text
    generated = text.split("Generated: ", 1)[1].splitlines()[0]
    assert datetime.fromisoformat(generated).tzinfo is not None
    for row in expected.data["rows"]:
        assert row["workerName"] in text
        assert str(row["hours"]) in text
        assert str(row["cost"]) in text
    assert "April worker" not in text
    assert "Other cycle" not in text
    _, april_text = pdf_text(client.get(EXPORT, {
        **filters, "startDate": "2026-04-01", "endDate": "2026-04-30",
        "exportFormat": "pdf",
    }))
    assert "April worker" in april_text
    assert "Worker 00" not in april_text


def test_pdf_period_id_empty_and_scoping(client, cycle):
    built = cycle()
    farm = Farm.objects.get()
    local_cycle = CropCycle.objects.get(pk=built["cycle"]["id"])
    add_record(farm, local_cycle, "Local worker", date(2026, 3, 15))
    period = ReportingPeriod.objects.create(
        farm=farm, name="March", start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    foreign_owner = User.objects.create_user(
        email="pdf-foreign@agrivanta.test", password="ExamplePassword123!"
    )
    foreign = Farm.objects.create(owner=foreign_owner, name="Foreign farm")
    field = Field.objects.create(farm=foreign, name="Foreign field", area=1)
    crop = Crop.objects.create(farm=foreign, name="Foreign crop")
    foreign_cycle = CropCycle.objects.create(
        farm=foreign, field=field, crop=crop, cycle_type="annual",
        start_date=date(2026, 1, 1),
    )
    add_record(foreign, foreign_cycle, "Foreign worker", date(2026, 3, 15))
    _, text = pdf_text(client.get(EXPORT, {
        "exportFormat": "pdf", "periodId": str(period.id),
    }))
    assert "2026-03-01 to 2026-03-31" in text
    assert "Local worker" in text
    assert "Foreign worker" not in text
    assert client.get(EXPORT, {
        "exportFormat": "pdf", "cycleId": str(foreign_cycle.id),
    }).status_code == 400
    assert client.get(EXPORT, {
        "exportFormat": "pdf", "farmId": str(foreign.id),
    }).status_code == 404
    foreign_period = ReportingPeriod.objects.create(
        farm=foreign, name="Foreign period", start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    assert client.get(EXPORT, {
        "exportFormat": "pdf", "periodId": str(foreign_period.id),
    }).status_code == 400
    _, empty = pdf_text(client.get(EXPORT, {
        "exportFormat": "pdf", "startDate": "2027-01-01",
        "endDate": "2027-01-31",
    }))
    assert "No data for this period." in empty
    assert "Local worker" not in empty


@pytest.mark.parametrize("report_name", [
    "profitability", "budget-vs-actual", "activity-status", "inventory",
    "labour-usage", "equipment-usage", "dashboard",
])
def test_all_report_types_have_valid_pdf(client, report_name):
    response = client.get(
        f"/api/reports/{report_name}/export", {"exportFormat": "pdf"}
    )
    _, text = pdf_text(response)
    assert "Farm:" in text
    assert "Reporting period:" in text
    assert "Generated:" in text


def test_pdf_requires_authentication_and_valid_filters(anon, client):
    assert anon.get(EXPORT, {"exportFormat": "pdf"}).status_code == 401
    assert client.get(EXPORT, {
        "exportFormat": "pdf", "startDate": "2026-03-01",
    }).status_code == 400
    assert client.get(
        "/api/reports/unknown/export", {"exportFormat": "pdf"}
    ).status_code == 404


def test_pdf_escapes_report_data(client, cycle):
    built = cycle()
    farm = Farm.objects.get()
    crop_cycle = CropCycle.objects.get(pk=built["cycle"]["id"])
    add_record(
        farm, crop_cycle, "<img src='https://invalid.example/x'>",
        date(2026, 3, 15),
    )
    _, text = pdf_text(client.get(EXPORT, {"exportFormat": "pdf"}))
    assert "<img src='https://invalid.example/x'>" in text


def test_renderer_blocks_scripts_and_network_requests():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/leak"
        content = render_chromium_pdf(
            f"<p>Safe content</p><img src='{url}'>"
            f"<script>document.write('Script ran');fetch('{url}')</script>"
        )
        text = "\n".join(
            page.extract_text() for page in PdfReader(BytesIO(content)).pages
        )
        assert "Safe content" in text
        assert "Script ran" not in text
        assert requests == []
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_missing_browser_returns_503_and_cleans_runtime(client, monkeypatch):
    from api import pdf_chromium

    monkeypatch.setenv("REPORT_PDF_CHROMIUM_EXECUTABLE", "missing-browser")
    response = client.get(EXPORT, {"exportFormat": "pdf"})
    assert response.status_code == 503
    runtime = Path(pdf_chromium.__file__).resolve().parent.parent / ".pdf-runtime"
    assert not list(runtime.iterdir())


def test_renderer_timeout_terminates_process_and_cleans_runtime(monkeypatch):
    from api import pdf_chromium
    from api.exceptions import ApiError

    process = Mock(pid=1234)
    process.communicate.side_effect = [
        subprocess.TimeoutExpired("renderer", 60), (b"", b"")
    ]
    monkeypatch.setattr(pdf_chromium, "_browser_executable", lambda: "browser")
    monkeypatch.setattr(pdf_chromium.subprocess, "Popen", lambda *a, **k: process)
    terminate = Mock()
    monkeypatch.setattr(pdf_chromium, "_terminate_renderer", terminate)
    with pytest.raises(ApiError) as error:
        render_chromium_pdf("<p>test</p>")
    assert error.value.status_code == 503
    terminate.assert_called_once_with(process)
    runtime = Path(pdf_chromium.__file__).resolve().parent.parent / ".pdf-runtime"
    assert not list(runtime.iterdir())
