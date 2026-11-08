from pathlib import Path

from django.http import HttpResponse
from django.views.decorators.http import require_GET

SCHEMA_PATH = Path(__file__).with_name("openapi.yaml")


@require_GET
def openapi_schema(request):
    return HttpResponse(
        SCHEMA_PATH.read_bytes(),
        content_type="application/yaml; charset=utf-8",
    )
