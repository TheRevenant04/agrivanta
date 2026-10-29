import time
import uuid

import structlog
from django.db import DatabaseError, connection
from django.http import JsonResponse
from structlog.contextvars import bind_contextvars, clear_contextvars

logger = structlog.get_logger(__name__)


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
                logger.exception(
                    "http_request_failed",
                    method=request.method,
                    path=request.path,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                raise

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
