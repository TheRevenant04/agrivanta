from django.conf import settings
from django.contrib import admin
from django.http import Http404, HttpResponse
from django.urls import include, path, re_path
from pathlib import Path

from api.observability import healthz, readyz
from api.schema import openapi_schema


def index_view(request):
    index_path = Path(settings.STATIC_ROOT) / "index.html"
    if not index_path.exists():
        index_path = settings.BASE_DIR / "frontend_dist" / "index.html"
    if not index_path.exists():
        index_path = settings.BASE_DIR.parent / "frontend" / "dist" / "index.html"

    if index_path.exists():
        return HttpResponse(index_path.read_text(encoding="utf-8"))
    raise Http404("Frontend index.html not found.")


urlpatterns = [
    path("healthz", healthz),
    path("readyz", readyz),
    path("openapi.yaml", openapi_schema, name="openapi-schema"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    re_path(r"^.*$", index_view, name="index"),
]
