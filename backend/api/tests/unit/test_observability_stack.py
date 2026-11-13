"""Static checks for the optional observability Compose stack.

No Docker daemon is required. These tests assert the checked-in configuration
keeps the independent observability project, collector fan-out, provisioned
dashboard, and alert contract described in issue #146.
"""

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
OBS = REPO_ROOT / "observability"

OBS_COMPOSE = OBS / "docker-compose.yml"
ROOT_COMPOSE = REPO_ROOT / "docker-compose.yml"
COLLECTOR_CONFIG = OBS / "otel-collector" / "config.yaml"
PROMETHEUS_ALERTS = OBS / "prometheus" / "alerts.yml"
GRAFANA_ALERTING = OBS / "grafana" / "provisioning" / "alerting" / "alerting.yaml"
DASHBOARD = OBS / "grafana" / "dashboards" / "agrivanta-product-metrics.json"
README = OBS / "README.md"

OBS_SERVICES = {"otel-collector", "prometheus", "loki", "tempo", "grafana"}
APP_SERVICES = {"web", "celery-worker", "postgres", "redis", "frontend"}
PRODUCT_METRICS = {
    "agrivanta_farms_created",
    "agrivanta_users_active",
    "agrivanta_records_created",
    "agrivanta_record_creation_failures",
}


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _all_target_expressions(dashboard: dict) -> list[str]:
    expressions = []
    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            expressions.append(target["expr"])
    return expressions


def test_observability_compose_is_a_separate_standalone_project():
    compose = _load_yaml(OBS_COMPOSE)

    assert compose["name"] == "agrivanta-observability"
    services = compose["services"]
    assert set(services) == OBS_SERVICES
    assert not APP_SERVICES & set(services)

    for service in services.values():
        depends_on = service.get("depends_on", [])
        if isinstance(depends_on, dict):
            depends_on = depends_on.keys()
        assert not APP_SERVICES & set(depends_on)

    collector_ports = " ".join(services["otel-collector"]["ports"])
    grafana_ports = " ".join(services["grafana"]["ports"])
    assert "4318" in collector_ports
    assert "3000" in grafana_ports


def test_root_compose_does_not_start_observability_services():
    compose = _load_yaml(ROOT_COMPOSE)
    assert not OBS_SERVICES & set(compose["services"])


def test_collector_routes_each_signal_to_its_backend():
    config = _load_yaml(COLLECTOR_CONFIG)
    pipelines = config["service"]["pipelines"]

    assert "otlp/tempo" in pipelines["traces"]["exporters"]
    assert "loki" in pipelines["logs"]["exporters"]
    assert "prometheus" in pipelines["metrics"]["exporters"]


def test_dashboard_shows_every_product_metric_and_filters_every_panel():
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    expressions = _all_target_expressions(dashboard)

    for metric in PRODUCT_METRICS:
        assert any(metric in expression for expression in expressions), metric

    variables = {
        variable["name"] for variable in dashboard["templating"]["list"]
    }
    assert {"environment", "deployed_version"} <= variables

    for panel in dashboard["panels"]:
        targets = panel.get("targets", [])
        assert targets, panel["title"]
        for target in targets:
            assert "$environment" in target["expr"], panel["title"]
            assert "$deployed_version" in target["expr"], panel["title"]


def test_prometheus_alert_documents_thresholds_and_actionable_metadata():
    alerts = _load_yaml(PROMETHEUS_ALERTS)
    (group,) = alerts["groups"]
    (rule,) = group["rules"]

    expression = rule["expr"]
    assert rule["alert"] == "AgrivantaRecordCreationFailures"
    assert rule["for"] == "10m"
    assert "[5m]" in expression
    assert "> 10" in expression
    assert "0.05" in expression
    assert "agrivanta_record_creation_failures_total" in expression
    assert "agrivanta_records_created_total" in expression

    assert rule["labels"]["owner"] == "agrivanta-backend"
    annotations = rule["annotations"]
    assert annotations["owner"] == "agrivanta-backend"
    assert "dashboard_url" in annotations
    assert "runbook_url" in annotations


def test_grafana_alert_uses_local_webhook_and_documents_payload():
    alerting = _load_yaml(GRAFANA_ALERTING)

    receiver = alerting["contactPoints"][0]["receivers"][0]
    assert receiver["type"] == "webhook"
    assert "url" in receiver["settings"]

    (group,) = alerting["groups"]
    (rule,) = group["rules"]
    assert rule["for"] == "10m"
    expression = rule["data"][0]["model"]["expr"]
    assert "> bool 10" in expression
    assert "0.05" in expression

    annotations = rule["annotations"]
    for key in (
        "service",
        "environment",
        "deployed_version",
        "owner",
        "dashboard_url",
        "runbook_url",
    ):
        assert key in annotations


def test_readme_documents_optional_stack_and_runbook():
    content = README.read_text(encoding="utf-8")

    assert "optional" in content.lower()
    assert "agrivanta-observability" in content
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in content
    assert "## Alert runbook: record-creation failures" in content
    assert "localhost:3000" in content
