# Agrivanta observability stack

This is an **optional, standalone observability stack** for local development
and demos. It runs as its own Compose project (`agrivanta-observability`) on its
own Docker network. It starts no application services, and the application
Compose project (`agrivanta-dev` / `agrivanta-prod`) never depends on it.

The stack contains:

| Service | Purpose | Published port |
| --- | --- | --- |
| `otel-collector` | OTLP receiver, fan-out to Tempo/Loki/Prometheus | `4318` (OTLP/HTTP) |
| `prometheus` | Metrics storage plus alert rules | `9090` |
| `loki` | Log storage | internal only |
| `tempo` | Trace storage | internal only |
| `grafana` | Provisioned datasources, dashboard, alerts | `3000` |

Only the ports above are published. Set `OTEL_COLLECTOR_PORT`,
`PROMETHEUS_PORT`, or `GRAFANA_PORT` to change the host ports.

## Start and stop

```bash
# Start (from the repository root)
docker compose -f observability/docker-compose.yml up -d

# Stop and remove containers, keeping data volumes
docker compose -f observability/docker-compose.yml down

# Stop and delete stored telemetry too
docker compose -f observability/docker-compose.yml down -v
```

Grafana opens at <http://localhost:3000>. Anonymous admin access is enabled for
local use only. Prometheus is at <http://localhost:9090>.

## Point the backend at the collector

Telemetry is opt-in. If `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, the backend
starts no exporters and remains fully offline/no-op.

Run the backend directly on the host:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_SERVICE_NAME=agrivanta-backend
export OTEL_DEPLOYMENT_ENVIRONMENT=local
export AGRIVANTA_VERSION=$(git rev-parse --short HEAD)
export AGRIVANTA_REVISION=$(git rev-parse HEAD)
uv run python backend/manage.py runserver
```

Run the application Compose stack and send telemetry through the host gateway:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318
docker compose up --build
```

Docker Desktop resolves `host.docker.internal` automatically. On Linux, add
`extra_hosts: ["host.docker.internal:host-gateway"]` to the `web` and
`celery-worker` services (or use the Docker bridge gateway address) and ensure
the collector publishes `4318` on an address reachable from containers. The
collector binds `0.0.0.0:4318` by default so the host gateway can reach it; set
`OTEL_COLLECTOR_BIND=127.0.0.1` if you only need host-local access.

Supported environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset (telemetry disabled) | OTLP/HTTP base URL |
| `OTEL_SERVICE_NAME` | `agrivanta-backend` | `service.name` resource attribute |
| `OTEL_DEPLOYMENT_ENVIRONMENT` | `local` | One of `local`, `dev`, `staging`, `production`; invalid values fall back to `local` |
| `AGRIVANTA_VERSION` | `local` | `service.version` and the `deployed_version` metric label |
| `AGRIVANTA_REVISION` | unset | Added as `service.revision` when set and not `unknown` |

Traces, metrics, and JSON logs are exported over OTLP/HTTP to
`/v1/traces`, `/v1/metrics`, and `/v1/logs`. Export failures are logged by the
OpenTelemetry exporter on a background thread and never fail API requests or
Celery tasks.

## Where to look

- **Dashboard**: Grafana → Agrivanta → *Agrivanta Product Metrics*
  (<http://localhost:3000/d/agrivanta-product-metrics>).
  The `environment` and `deployed_version` template variables filter every
  panel.
- **Traces**: Grafana → Explore → Tempo. Requests and Celery tasks share a
  trace ID; spans cover Django/DRF, psycopg (PostgreSQL), Celery, Redis, and
  outbound HTTP.
- **Logs**: Grafana → Explore → Loki. JSON logs include `correlation_id`,
  `trace_id`, and `span_id`.
- **Alert state**: Grafana → Alerting → Alert rules →
  *Agrivanta record-creation failures*, or Prometheus → Alerts
  (<http://localhost:9090/alerts>).

The four product metrics are:

- `agrivanta.farms.created`
- `agrivanta.users.active`
- `agrivanta.records.created`
- `agrivanta.record_creation.failures`

Every metric carries `service`, `environment`, and `deployed_version` labels.
Failure metrics additionally carry the route template as `endpoint` and a
coarse `reason` (`client_error` or `server_error`). No user, farm, or record
IDs, payloads, credentials, or farm-record values are used as attributes.

## Alert threshold rationale

The record-creation-failure alert fires when **either** condition holds for
**10 minutes**:

1. more than **10** failed create requests in the last **5 minutes**, or
2. more than **5%** of create attempts fail.

Rationale: activities, expenses, harvests, and sales are the user's core
operational and financial records. More than ten failures in five minutes
(roughly two per minute) means multiple users are probably unable to record
work or money, which can cause duplicate entries and incomplete reporting.
Requiring the condition to hold for ten minutes suppresses transient blips
such as a single bad client request or a short deploy. The 5% ratio catches
high-traffic deployments where an absolute count alone would be slow to
trigger. The ratio denominator combines `agrivanta_records_created_total` and
`agrivanta_record_creation_failures_total`.

The notification payload includes `service`, `environment`, `deployed_version`,
`owner` (`agrivanta-backend`), a dashboard URL filtered to the affected
environment/version, and a runbook URL. Notifications use a local webhook
contact point (`http://127.0.0.1:9099/alerts`) so no external paging
credentials are committed. Point it at your own receiver if desired.

## Alert runbook: record-creation failures

1. Open the dashboard URL from the notification and confirm which endpoint and
   `reason` are failing.
2. Check Grafana → Explore → Loki for `http_request` entries with the matching
   `trace_id`; 5xx/`server_error` usually indicates a backend regression, a
   database problem, or an unavailable dependency.
3. Check Grafana → Explore → Tempo for the same trace ID and identify the
   failing span (Django, PostgreSQL, Redis, Celery, or outbound HTTP).
4. Validate the database and Redis are healthy (`/healthz`, `/readyz`) and
   review recent deploys for `deployed_version`.
5. If the failure is client-driven (4xx/`client_error`), check request
   validation changes or a bad client release.
6. After the fix, confirm the alert returns to Normal in Grafana → Alerting.

To exercise the alert locally, send more than ten failing create requests in
five minutes from an authenticated session (for example invalid
`POST /api/expenses` payloads) and keep the failure rate elevated for ten
minutes. Stop the failures to watch the alert resolve.

## Layout

```text
observability/
  docker-compose.yml
  otel-collector/config.yaml     # OTLP receivers and Tempo/Loki/Prometheus fan-out
  prometheus/prometheus.yml      # scrapes the collector
  prometheus/alerts.yml          # record-creation failure alert
  loki/config.yaml
  tempo/config.yaml
  grafana/provisioning/          # datasources, dashboard provider, alerting
  grafana/dashboards/            # versioned dashboard JSON
```
