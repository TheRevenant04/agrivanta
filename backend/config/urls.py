from django.contrib import admin
from django.urls import include, path

from api.observability import healthz, readyz
from api.schema import openapi_schema

urlpatterns = [
    path("healthz", healthz),
    path("readyz", readyz),
    path("openapi.yaml", openapi_schema, name="openapi-schema"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
