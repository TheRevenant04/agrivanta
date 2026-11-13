import time
import uuid

import structlog
from django.db import DatabaseError, connection
from django.http import JsonResponse
from structlog.contextvars import bind_contextvars, clear_contextvars

from .telemetry import (
    record_active_user,
    record_record_creation_failure,
)

logger = structlog.get_logger(__name__)

# Route templates (never raw paths) for the create endpoints tracked by the
# record-creation failure metric.
RECORD_CREATE_ROUTES = {
    "api/activities": "activity",
    "api/expenses": "expense",
    "api/harvests": "harvest",
    "api/sales": "sale",
}


def _record_request_telemetry(request, status_code=None):
    try:
        record_active_user(getattr(request, "user", None))
    except Exception:  # pragma: no cover - telemetry must never break requests
        pass

    if status_code is None or request.method != "POST":
        return
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", "") if match is not None else ""
    if route not in RECORD_CREATE_ROUTES or status_code < 400:
        return
    reason = "server_error" if status_code >= 500 else "client_error"
    record_record_creation_failure(endpoint=route, reason=reason)


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = str(uuid.uuid4())
        clear_contextvars()
        bind_contextvars(correlation_id=correlation_id)
        started = time.perf_counter()

        try:
            try:
                response = self.get_response(request)
            except Exception:
                _record_request_telemetry(request, status_code=500)
                logger.exception(
                    "http_request_failed",
                    method=request.method,
                    path=request.path,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                raise

            _record_request_telemetry(
                request, status_code=response.status_code
            )
            response["X-Correlation-ID"] = correlation_id
            logger.info(
                "http_request",
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return response
        finally:
            clear_contextvars()


def healthz(request):
    return JsonResponse({"status": "ok"})


def readyz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
