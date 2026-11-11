from pathlib import Path

from django.test import Client


def test_openapi_endpoint_publishes_backend_schema():
    schema_path = Path(__file__).parents[1] / "openapi.yaml"
    response = Client().get("/openapi.yaml")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/yaml; charset=utf-8"
    assert response.content == schema_path.read_bytes()
    schema = response.content.decode().replace("\r\n", "\n")
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
    assert (
        "- name: crop\n"
        "          in: query\n"
        "          required: false\n"
        "          description: Only return varieties of this crop.\n"
        "          schema:\n"
        "            type: string"
    ) in schema
    assert "format: binary" in schema
    assert "Each line is a\n                  ChatStreamEvent." in schema
    chat_path = schema.split("  /chat:\n", maxsplit=1)[1].split(
        "\n  /imports/preview:", maxsplit=1
    )[0]
    for status_code in ("'400'", "'503'"):
        assert f"        {status_code}:\n" in chat_path
    assert chat_path.count("$ref: '#/components/schemas/Error'") == 2


def test_openapi_endpoint_is_read_only():
    response = Client().post("/openapi.yaml")

    assert response.status_code == 405
