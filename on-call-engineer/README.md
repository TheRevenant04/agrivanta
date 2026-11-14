# On-call engineer alert poller

`on_call_agent.py` polls an observability alert API on a fixed interval and, when
active/firing alerts are detected, extracts alert details and passes them to a
headless coding agent runner/invocation.

The implementation is self-contained in `on-call-engineer/` and does not modify
core Agrivanta backend APIs.

## What it does

1. Polls a configured alert endpoint (default: Prometheus alerts API) every 60
   seconds (configurable).
2. Parses common alert payload shapes (Prometheus, Alertmanager/Grafana-style
   list/object payloads).
3. Detects active/firing alerts (`firing`/`active`/`alerting`, including nested
   `status.state`).
4. Extracts normalized details (name, severity, service, environment, deployed
   version, summary/description, timestamps, labels/annotations, raw alert).
5. Invokes a headless coding agent command per newly detected alert (or logs the
   alert if no command is configured).
6. Handles API/network/JSON errors gracefully and continues polling.
7. Deduplicates alerts within a run (by fingerprint/identity) to avoid repeated
   invocations on every poll.

## Requirements

- Python 3.13+ (repo default)
- No additional dependencies beyond the Python standard library for this script

## Setup

From the repository root:

```powershell
# optional: choose a specific Python/venv
python --version
```

No installation step is required; run the script directly.

## Usage

Basic polling against a local Prometheus instance:

```powershell
python on-call-engineer/on_call_agent.py --alert-url http://localhost:9090/api/v1/alerts
```

Single poll (useful for cron/tests/smoke checks):

```powershell
python on-call-engineer/on_call_agent.py --alert-url http://localhost:9090/api/v1/alerts --once
```

Invoke a headless coding agent when a firing alert is detected:

```powershell
python on-call-engineer/on_call_agent.py `
  --alert-url http://localhost:9090/api/v1/alerts `
  --agent-command 'opencode run --agent software-engineer --auto "Investigate this observability alert: {alert_json}"'
```

Or pass the alert JSON via a temporary `.json` file:

```powershell
python on-call-engineer/on_call_agent.py `
  --alert-url http://localhost:9090/api/v1/alerts `
  --agent-command "my-agent-runner --alert-file {alert_file}"
```

The command template is tokenized with `shlex.split` and executed directly
without a shell (`shell=False`). `{alert_json}` is substituted inside the
matching argument token with the JSON alert payload, and `{alert_file}` writes
the JSON payload to a temporary `.json` file that is removed after the runner
completes. Literal `{...}` braces in other parts of the command template are
preserved untouched. If `--agent-command`/`AGENT_COMMAND` is not set, the script
logs firing alerts and does not execute an external runner.

## Configuration

CLI flags take precedence over environment variables.

| Setting | CLI flag | Environment variable | Default | Description |
| --- | --- | --- | --- | --- |
| Alert endpoint | `--alert-url` | `ALERT_API_URL` | `http://localhost:9090/api/v1/alerts` | Observability alert API URL (`http`/`https`) to poll |
| Poll interval | `--interval` | `POLL_INTERVAL_SECONDS` | `60` | Seconds between polls |
| HTTP timeout | `--timeout` | `ALERT_API_TIMEOUT_SECONDS` | `10` | HTTP request timeout in seconds |
| Agent command | `--agent-command` | `AGENT_COMMAND` | *(empty)* | Command template invoked per firing alert (`shell=False`); supports `{alert_json}` and `{alert_file}` |
| Agent timeout | `--agent-timeout` | `AGENT_TIMEOUT_SECONDS` | `300` | Subprocess timeout in seconds (`0` = disabled) |
| Single poll | `--once` | `POLL_ONCE` | `false` | Poll once and exit |
| Max polls | `--max-polls` | `MAX_POLLS` | `0` | Stop after N polls (`0` = unlimited) |
| Log level | `--log-level` | `LOG_LEVEL` | `INFO` | Python logging level |

Example with environment variables:

```powershell
$env:ALERT_API_URL = "http://localhost:9093/api/v2/alerts"
$env:POLL_INTERVAL_SECONDS = "60"
$env:AGENT_COMMAND = "opencode run --agent software-engineer --auto 'Handle alert: {alert_json}'"
python on-call-engineer/on_call_agent.py
```

## Supported alert payload shapes

The poller is tolerant of common observability API responses, including:

- Prometheus alerts API: `{"status":"success","data":{"alerts":[...]}}`
- Prometheus rules API: `{"status":"success","data":{"rules":[...]}}`
- Alertmanager/Grafana-style collections: `{"alerts":[...]}` / `{"instances":[...]}`
- Top-level alert arrays: `[...]`
- Single alert objects

Prometheus `"status": "error"` responses are logged as poll errors rather than
treated as empty alert sets. Alerts are treated as active/firing when
state/status indicates `firing`, `active`, or `alerting` (or equivalent boolean
flags).

## Error handling and reliability

- HTTP/network failures, disallowed URL schemes, timeouts, API error payloads,
  and invalid JSON are logged and do not crash the polling loop.
- Agent invocation failures (non-zero exit codes, `OSError`, or subprocess
  timeouts) are caught and logged per alert; failed alerts are not marked
  handled and will be retried on the next poll, while polling continues.
- Dedupe tracks currently active alerts so an alert is not re-invoked while
  continuously firing, and clears resolved alerts when they leave the active
  set so re-firing alerts trigger again.
- `--once`/`--max-polls` allow deterministic runs in tests and scheduled jobs.

## Testing

Run the unit tests for the alert poller:

```powershell
uv run pytest on-call-engineer/tests
```

Tests cover polling flow, alert extraction/handling, agent invocation behavior,
and error handling with mocked fetch/sleep/invoker functions (no live external
alert service required).

## Notes

- This is a local/on-call automation helper; it does not deploy infrastructure.
- Configure the agent command according to your environment and security policy.
- Because alert payloads may contain operational details, review logging/redaction
  needs before using in production environments.
