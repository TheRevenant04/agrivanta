"""OpenTelemetry setup and product metrics.

Telemetry is optional. When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset the
module behaves as a no-op: it imports no OpenTelemetry SDK or instrumentation
packages, starts no exporter threads, and never touches the network. This keeps
local development, management commands, Celery, and ``pytest`` hermetic.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from typing import Any, Callable

from django.conf import settings

logger = logging.getLogger(__name__)

FARMS_CREATED = "agrivanta.farms.created"
USERS_ACTIVE = "agrivanta.users.active"
RECORDS_CREATED = "agrivanta.records.created"
RECORD_CREATION_FAILURES = "agrivanta.record_creation.failures"

PRODUCT_METRIC_NAMES = (
    FARMS_CREATED,
    USERS_ACTIVE,
    RECORDS_CREATED,
    RECORD_CREATION_FAILURES,
)

DEFAULT_SERVICE_NAME = "agrivanta-backend"
DEFAULT_ENVIRONMENT = "local"
ALLOWED_ENVIRONMENTS = frozenset(
    {"local", "dev", "staging", "production"}
)
ACTIVE_USER_WINDOW_SECONDS = 300
_METRIC_NAME = "agrivanta"

_INIT_LOCK = threading.Lock()
_initialized = False
_enabled = False
_product_metrics: "ProductMetrics | None" = None
_provider_shutdown: Callable[[], None] | None = None


def service_name() -> str:
    return (
        getattr(settings, "OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
        or DEFAULT_SERVICE_NAME
    )


def deployment_environment() -> str:
    value = str(
        getattr(settings, "OTEL_DEPLOYMENT_ENVIRONMENT", DEFAULT_ENVIRONMENT)
        or DEFAULT_ENVIRONMENT
    ).strip().lower()
    return value if value in ALLOWED_ENVIRONMENTS else DEFAULT_ENVIRONMENT


def deployed_version() -> str:
    value = str(
        getattr(settings, "OTEL_SERVICE_VERSION", "") or ""
    ).strip()
    return value or "local"


def service_revision() -> str:
    value = str(
        getattr(settings, "AGRIVANTA_REVISION", "") or ""
    ).strip()
    return "" if value in ("", "unknown") else value


def resource_attributes() -> dict[str, str]:
    attributes = {
        "service.name": service_name(),
        "deployment.environment": deployment_environment(),
        "service.version": deployed_version(),
    }
    revision = service_revision()
    if revision:
        attributes["service.revision"] = revision
    return attributes


def metric_attributes(**extra: str) -> dict[str, str]:
    """Base labels shared by every product metric."""

    attributes = {
        "service": service_name(),
        "environment": deployment_environment(),
        "deployed_version": deployed_version(),
    }
    attributes.update(extra)
    return attributes


class ActiveUserTracker:
    """Process-local set of authenticated users seen in a rolling window."""

    def __init__(
        self,
        window_seconds: float = ACTIVE_USER_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.window_seconds = window_seconds
        self._clock = clock
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def record(self, user_id: Any) -> None:
        if user_id in (None, ""):
            return
        now = self._clock()
        with self._lock:
            self._seen[str(user_id)] = now

    def count(self) -> int:
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            expired = [
                user_id
                for user_id, last_seen in self._seen.items()
                if last_seen < cutoff
            ]
            for user_id in expired:
                self._seen.pop(user_id, None)
            return len(self._seen)


class _ExcludeOtelLogsFilter(logging.Filter):
    """Keep exporter/instrumentation logs out of the OTLP log pipeline."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("opentelemetry")


_active_users = ActiveUserTracker()


def record_active_user(user: Any) -> None:
    try:
        if user is None or not getattr(user, "is_authenticated", False):
            return
        _active_users.record(getattr(user, "pk", None))
    except Exception:  # pragma: no cover - telemetry must never break requests
        logger.debug("telemetry.active_user_failed", exc_info=True)


class ProductMetrics:
    """Creates and records the farm-domain product metrics."""

    def __init__(
        self,
        meter: Any,
        tracker: ActiveUserTracker | None = None,
    ) -> None:
        self._tracker = tracker or _active_users
        self._farms_created = meter.create_counter(
            FARMS_CREATED,
            unit="1",
            description="Farms created.",
        )
        self._records_created = meter.create_counter(
            RECORDS_CREATED,
            unit="1",
            description="Activity, expense, harvest, and sale records created.",
        )
        self._record_creation_failures = meter.create_counter(
            RECORD_CREATION_FAILURES,
            unit="1",
            description="Failed activity, expense, harvest, and sale creates.",
        )
        self._users_active = meter.create_observable_gauge(
            USERS_ACTIVE,
            callbacks=[self._observe_active_users],
            unit="1",
            description="Distinct authenticated users active in the last 5m.",
        )

    def _observe_active_users(self, options: Any) -> list[Any]:
        from opentelemetry.metrics import Observation

        return [
            Observation(
                self._tracker.count(),
                attributes=metric_attributes(),
            )
        ]

    def record_farm_created(self) -> None:
        self._farms_created.add(1, attributes=metric_attributes())

    def record_record_created(self, record_type: str) -> None:
        self._records_created.add(
            1,
            attributes=metric_attributes(record_type=record_type),
        )

    def record_record_creation_failure(
        self, endpoint: str, reason: str
    ) -> None:
        self._record_creation_failures.add(
            1,
            attributes=metric_attributes(endpoint=endpoint, reason=reason),
        )


def record_farm_created() -> None:
    try:
        if _product_metrics is not None:
            _product_metrics.record_farm_created()
    except Exception:  # pragma: no cover - telemetry must never break requests
        logger.debug("telemetry.farm_metric_failed", exc_info=True)


def record_record_created(record_type: str) -> None:
    try:
        if _product_metrics is not None:
            _product_metrics.record_record_created(record_type)
    except Exception:  # pragma: no cover - telemetry must never break requests
        logger.debug("telemetry.record_metric_failed", exc_info=True)


def record_record_creation_failure(endpoint: str, reason: str) -> None:
    try:
        if _product_metrics is not None:
            _product_metrics.record_record_creation_failure(endpoint, reason)
    except Exception:  # pragma: no cover - telemetry must never break requests
        logger.debug("telemetry.failure_metric_failed", exc_info=True)


def add_trace_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor that adds the active OpenTelemetry trace context."""

    try:
        from opentelemetry import trace

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            event_dict.setdefault(
                "trace_id", format(span_context.trace_id, "032x")
            )
            event_dict.setdefault(
                "span_id", format(span_context.span_id, "016x")
            )
    except Exception:  # pragma: no cover - logging must never fail
        pass
    return event_dict


def is_enabled() -> bool:
    return _enabled


def _otlp_signal_endpoint(endpoint: str, signal: str) -> str:
    base = endpoint.rstrip("/")
    if base.endswith(f"/{signal}"):
        return base
    return f"{base}/{signal}"


def _configure_instrumentation(tracer_provider: Any) -> None:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    instrumentors = (
        DjangoInstrumentor(),
        CeleryInstrumentor(),
        PsycopgInstrumentor(),
        RedisInstrumentor(),
        HTTPXClientInstrumentor(),
        RequestsInstrumentor(),
    )
    for instrumentor in instrumentors:
        try:
            instrumentor.instrument(tracer_provider=tracer_provider)
        except Exception:  # pragma: no cover - one integration must not stop others
            logger.warning(
                "OpenTelemetry instrumentation failed for %s",
                type(instrumentor).__name__,
                exc_info=True,
            )


def _configure(endpoint: str) -> None:
    global _product_metrics, _provider_shutdown

    from opentelemetry import _logs, metrics, trace
    from opentelemetry.exporter.otlp.proto.http._log_exporter import (
        OTLPLogExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(resource_attributes())

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=_otlp_signal_endpoint(endpoint, "v1/traces")
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=_otlp_signal_endpoint(endpoint, "v1/metrics")
        )
    )
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[metric_reader]
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint=_otlp_signal_endpoint(endpoint, "v1/logs")
            )
        )
    )
    _logs.set_logger_provider(logger_provider)
    otel_log_handler = LoggingHandler(
        level=logging.NOTSET, logger_provider=logger_provider
    )
    otel_log_handler.addFilter(_ExcludeOtelLogsFilter())
    logging.getLogger().addHandler(otel_log_handler)

    _product_metrics = ProductMetrics(
        metrics.get_meter(_METRIC_NAME), tracker=_active_users
    )
    _configure_instrumentation(tracer_provider)

    def shutdown() -> None:
        for provider in (meter_provider, logger_provider, tracer_provider):
            try:
                provider.shutdown()
            except Exception:  # pragma: no cover - best-effort shutdown
                pass

    _provider_shutdown = shutdown
    atexit.register(shutdown)


def setup_telemetry() -> bool:
    """Initialise telemetry when an OTLP endpoint is configured."""

    global _initialized, _enabled

    with _INIT_LOCK:
        if _initialized:
            return _enabled
        _initialized = True

        endpoint = str(
            getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or ""
        ).strip()
        if not endpoint:
            logger.debug(
                "OpenTelemetry disabled: OTEL_EXPORTER_OTLP_ENDPOINT unset"
            )
            _enabled = False
            return False

        try:
            _configure(endpoint)
        except Exception:  # pragma: no cover - never break the app
            logger.warning(
                "OpenTelemetry setup failed; continuing without telemetry",
                exc_info=True,
            )
            _enabled = False
            return False

        _enabled = True
        return True
