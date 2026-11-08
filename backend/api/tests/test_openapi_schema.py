from pathlib import Path

from django.test import Client


def test_openapi_endpoint_publishes_backend_schema():
    schema_path = Path(__file__).parents[1] / "openapi.yaml"
    response = Client().get("/openapi.yaml")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/yaml; charset=utf-8"
    assert response.content == schema_path.read_bytes()
    schema = response.content.decode()
    for service_path in (
        "  /chat:",
        "  /imports/preview:",
        "  /imports/commit:",
        "  /notifications:",
        "  /reporting-periods:",
        "  /dashboard:",
        "  /reports/{reportName}:",
    ):
        assert service_path in schema


def test_openapi_endpoint_is_read_only():
    response = Client().post("/openapi.yaml")

    assert response.status_code == 405
