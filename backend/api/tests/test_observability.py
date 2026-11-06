import json
import logging
from unittest.mock import patch

import pytest
import sentry_sdk
from django.db.utils import OperationalError
from django.test import Client, override_settings
from django.urls import path
from sentry_sdk.envelope import Envelope
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.transport import Transport
from structlog.stdlib import ProcessorFormatter


def deliberate_failure(request):
    raise RuntimeError("synthetic backend failure")


urlpatterns = [path("test-error", deliberate_failure)]


class RecordingTransport(Transport):
    instances = []

    def __init__(self, options=None):
        super().__init__(options)
        self.events = []
        self.instances.append(self)

    def capture_envelope(self, envelope: Envelope):
        for item in envelope.items:
            if item.type == "event":
                event = item.get_event()
                if event is not None:
                    self.events.append(event)

    def flush(self, timeout, callback=None):
        if callback:
            callback()

    def kill(self):
        pass


@pytest.mark.django_db
def test_health_endpoints_are_public_and_check_database(anon):
    health_response = anon.get("/healthz")
    ready_response = anon.get("/readyz")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readyz_returns_503_when_database_connection_fails(anon):
    with patch(
        "api.observability.connection.cursor",
        side_effect=OperationalError("database is unavailable"),
    ):
        response = anon.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.django_db
def test_request_log_is_json_and_correlation_id_is_returned(anon, caplog):
    first_response = anon.get("/healthz")
    second_response = anon.get("/healthz")
    first_id = first_response["X-Correlation-ID"]
    second_id = second_response["X-Correlation-ID"]

    assert first_id
    assert second_id
    assert first_id != second_id

    record = next(
        record
        for record in caplog.records
        if record.name == "api.observability"
        and isinstance(record.msg, dict)
        and record.msg.get("event") == "http_request"
    )
    formatter = next(
        handler.formatter
        for handler in logging.getLogger().handlers
        if isinstance(handler.formatter, ProcessorFormatter)
    )
    event = json.loads(formatter.format(record))
    assert event["correlation_id"] in {first_id, second_id}
    assert event["method"] == "GET"
    assert event["path"] == "/healthz"
    assert event["status_code"] == 200


@pytest.mark.django_db
def test_backend_exception_is_reported_to_sentry():
    RecordingTransport.instances.clear()
    global_scope = sentry_sdk.get_global_scope()
    previous_client = global_scope.client
    client = sentry_sdk.Client(
        dsn="http://public@example.com/1",
        integrations=[DjangoIntegration()],
        transport=RecordingTransport,
    )
    global_scope.set_client(client)
    try:
        with override_settings(ROOT_URLCONF=__name__):
            response = Client(raise_request_exception=False).get("/test-error")
        client.flush(timeout=2)
    finally:
        client.close()
        global_scope.set_client(previous_client)

    assert response.status_code == 500
    events = [
        event
        for transport in RecordingTransport.instances
        for event in transport.events
    ]
    assert any(
        exception.get("values", [{}])[0].get("type") == "RuntimeError"
        and exception.get("values", [{}])[0].get("value")
        == "synthetic backend failure"
        for event in events
        for exception in [event.get("exception", {})]
    )
