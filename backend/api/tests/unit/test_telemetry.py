"""Tests for the OpenTelemetry integration and product metrics.

These tests never configure an OTLP exporter. Metrics are collected through an
in-memory reader and traces use a local SDK provider, so the suite stays
hermetic and offline.
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from structlog.stdlib import ProcessorFormatter

from api import telemetry
from api.observability import _record_request_telemetry

REGISTER = "/api/auth/register"
REGISTER_PAYLOAD = {
    "name": "Telemetry Owner",
    "email": "telemetry@agrivanta.test",
    "password": "OliveHarvest#42",
}


def _collect(reader):
    result = {}
    data = reader.get_metrics_data()
    if data is None:
        return result
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                result[metric.name] = metric
    return result


def _points(reader, name):
    metric = _collect(reader).get(name)
    if metric is None:
        return []
    return list(metric.data.data_points)


def _sum(reader, name):
    return sum(point.value for point in _points(reader, name))


@pytest.fixture
def product_metrics(monkeypatch):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    tracker = telemetry.ActiveUserTracker()
    instance = telemetry.ProductMetrics(
        provider.get_meter("agrivanta-test"), tracker=tracker
    )
    monkeypatch.setattr(telemetry, "_product_metrics", instance)
    yield SimpleNamespace(
        reader=reader,
        provider=provider,
        tracker=tracker,
        instance=instance,
    )
    provider.shutdown()


def _formatter():
    return next(
        handler.formatter
        for handler in logging.getLogger().handlers
        if isinstance(handler.formatter, ProcessorFormatter)
    )


def test_telemetry_is_noop_without_otlp_endpoint(monkeypatch):
    monkeypatch.setattr(telemetry, "_initialized", False)
    monkeypatch.setattr(telemetry, "_enabled", False)
    monkeypatch.setattr(telemetry, "_product_metrics", None)

    with override_settings(OTEL_EXPORTER_OTLP_ENDPOINT=""):
        assert telemetry.setup_telemetry() is False

    assert telemetry.is_enabled() is False
    assert telemetry._product_metrics is None

    # All recording helpers are safe no-ops when telemetry is disabled.
    telemetry.record_farm_created()
    telemetry.record_record_created("activity")
    telemetry.record_record_creation_failure("api/expenses", "client_error")
    assert telemetry._product_metrics is None


def test_resource_attributes_use_configured_identity():
    with override_settings(
        OTEL_SERVICE_NAME="agrivanta-backend",
        OTEL_DEPLOYMENT_ENVIRONMENT="staging",
        OTEL_SERVICE_VERSION="1.2.3",
        AGRIVANTA_REVISION="abc123",
    ):
        assert telemetry.resource_attributes() == {
            "service.name": "agrivanta-backend",
            "deployment.environment": "staging",
            "service.version": "1.2.3",
            "service.revision": "abc123",
        }


def test_environment_and_version_fall_back_safely():
    with override_settings(
        OTEL_SERVICE_NAME="",
        OTEL_DEPLOYMENT_ENVIRONMENT="not-an-environment",
        OTEL_SERVICE_VERSION="",
        AGRIVANTA_REVISION="unknown",
    ):
        assert telemetry.service_name() == "agrivanta-backend"
        assert telemetry.deployment_environment() == "local"
        assert telemetry.deployed_version() == "local"
        assert "service.revision" not in telemetry.resource_attributes()


def test_metric_attributes_include_required_product_labels():
    with override_settings(
        OTEL_SERVICE_NAME="agrivanta-backend",
        OTEL_DEPLOYMENT_ENVIRONMENT="production",
        OTEL_SERVICE_VERSION="2026.11",
    ):
        assert telemetry.metric_attributes(record_type="expense") == {
            "service": "agrivanta-backend",
            "environment": "production",
            "deployed_version": "2026.11",
            "record_type": "expense",
        }


@pytest.mark.django_db
def test_registration_increments_farms_created(product_metrics, anon):
    response = anon.post(REGISTER, REGISTER_PAYLOAD, format="json")

    assert response.status_code == 201
    assert _sum(product_metrics.reader, telemetry.FARMS_CREATED) == 1
    (point,) = _points(product_metrics.reader, telemetry.FARMS_CREATED)
    assert point.attributes["service"] == "agrivanta-backend"
    assert point.attributes["environment"] == "local"
    assert point.attributes["deployed_version"] == "local"
    attributes = dict(point.attributes)
    assert "farm" not in " ".join(attributes).lower()
    assert response.data["user"]["id"] not in json.dumps(attributes)


def test_records_created_increment_for_each_record_type(
    product_metrics, client, setup, cycle
):
    built = cycle(setup())
    activity_type = client.get("/api/activity-types").data[0]

    activity = client.post(
        "/api/activities",
        {
            "cycleId": built["cycle"]["id"],
            "typeId": activity_type["id"],
            "plannedDate": "2026-03-10",
        },
        format="json",
    )
    expense = client.post(
        "/api/expenses",
        {
            "category": "inputs",
            "amount": "10",
            "date": "2026-03-11",
        },
        format="json",
    )
    harvest = client.post(
        "/api/harvests",
        {
            "cycleId": built["cycle"]["id"],
            "quantity": "100",
            "unitId": built["unit"]["id"],
            "date": "2026-08-01",
        },
        format="json",
    )
    customer = client.get("/api/customers").data[0]
    sale = client.post(
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest.data["id"],
            "quantity": "50",
            "unitPrice": "2",
            "date": "2026-08-02",
        },
        format="json",
    )

    assert activity.status_code == 201
    assert expense.status_code == 201
    assert harvest.status_code == 201
    assert sale.status_code == 201
    assert _sum(product_metrics.reader, telemetry.RECORDS_CREATED) == 4

    record_types = {
        point.attributes["record_type"]
        for point in _points(product_metrics.reader, telemetry.RECORDS_CREATED)
    }
    assert record_types == {"activity", "expense", "harvest", "sale"}
    for point in _points(product_metrics.reader, telemetry.RECORDS_CREATED):
        assert point.attributes["service"] == "agrivanta-backend"
        assert point.attributes["environment"] == "local"
        assert point.attributes["deployed_version"] == "local"


def test_record_creation_failures_count_client_errors_without_success(
    product_metrics, client
):
    invalid = client.post("/api/expenses", {}, format="json")
    assert invalid.status_code == 400

    (point,) = _points(
        product_metrics.reader, telemetry.RECORD_CREATION_FAILURES
    )
    assert point.value == 1
    assert point.attributes["endpoint"] == "api/expenses"
    assert point.attributes["reason"] == "client_error"
    assert point.attributes["service"] == "agrivanta-backend"
    assert point.attributes["environment"] == "local"
    assert point.attributes["deployed_version"] == "local"

    success = client.post(
        "/api/expenses",
        {"category": "inputs", "amount": "5", "date": "2026-03-11"},
        format="json",
    )
    assert success.status_code == 201
    assert (
        _sum(product_metrics.reader, telemetry.RECORD_CREATION_FAILURES) == 1
    )


def test_record_creation_failure_reason_distinguishes_server_errors():
    request = SimpleNamespace(
        method="POST",
        resolver_match=SimpleNamespace(route="api/harvests"),
    )
    with patch(
        "api.observability.record_active_user"
    ), patch(
        "api.observability.record_record_creation_failure"
    ) as failure:
        _record_request_telemetry(request, status_code=503)

    failure.assert_called_once_with(
        endpoint="api/harvests", reason="server_error"
    )


def test_active_users_counts_distinct_recent_users(product_metrics):
    clock = SimpleNamespace(now=1000.0)
    tracker = telemetry.ActiveUserTracker(
        window_seconds=300, clock=lambda: clock.now
    )
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    telemetry.ProductMetrics(
        provider.get_meter("agrivanta-active-users"), tracker=tracker
    )
    try:
        tracker.record("user-1")
        tracker.record("user-2")
        tracker.record("user-1")
        assert _points(reader, telemetry.USERS_ACTIVE)[0].value == 2

        clock.now += 301
        assert _points(reader, telemetry.USERS_ACTIVE)[0].value == 0

        tracker.record("user-1")
        assert _points(reader, telemetry.USERS_ACTIVE)[0].value == 1
    finally:
        provider.shutdown()


def test_request_middleware_records_active_user(
    monkeypatch, session, product_metrics
):
    clock = SimpleNamespace(now=1000.0)
    tracker = telemetry.ActiveUserTracker(
        window_seconds=300, clock=lambda: clock.now
    )
    monkeypatch.setattr(telemetry, "_active_users", tracker)

    response = session["client"].get("/api/auth/me")
    assert response.status_code == 200
    assert tracker.count() == 1

    session["client"].get("/api/auth/me")
    assert tracker.count() == 1

    clock.now += 301
    assert tracker.count() == 0


def test_http_request_log_has_trace_and_span_ids(anon, caplog):
    provider = TracerProvider()
    tracer = provider.get_tracer("agrivanta-test")
    with tracer.start_as_current_span("request") as span:
        span_context = span.get_span_context()
        response = anon.get("/healthz")

    assert response.status_code == 200
    record = next(
        record
        for record in caplog.records
        if record.name == "api.observability"
        and isinstance(record.msg, dict)
        and record.msg.get("event") == "http_request"
    )
    event = json.loads(_formatter().format(record))
    assert event["trace_id"] == format(span_context.trace_id, "032x")
    assert event["span_id"] == format(span_context.span_id, "016x")
    assert event["correlation_id"] == response["X-Correlation-ID"]
    provider.shutdown()


def test_stdlib_task_log_has_trace_and_span_ids(caplog):
    provider = TracerProvider()
    tracer = provider.get_tracer("agrivanta-test")
    logger = logging.getLogger("api.tasks")
    with tracer.start_as_current_span("celery_task") as span:
        span_context = span.get_span_context()
        logger.info("task_started")
        record = next(
            record
            for record in caplog.records
            if record.name == "api.tasks"
            and record.msg == "task_started"
        )
        event = json.loads(_formatter().format(record))

    assert event["trace_id"] == format(span_context.trace_id, "032x")
    assert event["span_id"] == format(span_context.span_id, "016x")
    provider.shutdown()
