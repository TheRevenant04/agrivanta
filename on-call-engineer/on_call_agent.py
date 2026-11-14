#!/usr/bin/env python3
"""Poll an observability alert API and invoke a headless coding agent on firing alerts.

Designed to run without a live external service: HTTP fetching, sleeping, and agent
invocation are injectable for tests.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence
from urllib import error, parse, request

logger = logging.getLogger("on_call_engineer")

Alert = dict[str, Any]
FetchAlerts = Callable[[str, float, Mapping[str, str]], list[Alert] | dict[str, Any]]
InvokeAgent = Callable[[Alert, "Config"], Any]
SleepFn = Callable[[float], None]


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, value, default)
        return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, value, default)
        return default


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll an observability alert API and invoke a headless coding agent for firing alerts.",
    )
    parser.add_argument(
        "--alert-url",
        default=os.getenv("ALERT_API_URL", "http://localhost:9090/api/v1/alerts"),
        help="Alert API endpoint to poll (env: ALERT_API_URL).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=_env_float("POLL_INTERVAL_SECONDS", 60.0),
        help="Polling interval in seconds (env: POLL_INTERVAL_SECONDS, default: 60).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_env_float("ALERT_API_TIMEOUT_SECONDS", 10.0),
        help="HTTP timeout in seconds (env: ALERT_API_TIMEOUT_SECONDS, default: 10).",
    )
    parser.add_argument(
        "--agent-command",
        default=os.getenv("AGENT_COMMAND", ""),
        help=(
            "Command template to invoke for each firing alert. Parsed with shlex.split and "
            "executed with shell=False; supports {alert_json} and {alert_file}. "
            "If omitted, alert details are logged (env: AGENT_COMMAND)."
        ),
    )
    parser.add_argument(
        "--agent-timeout",
        type=float,
        default=_env_float("AGENT_TIMEOUT_SECONDS", 300.0),
        help="Agent subprocess timeout in seconds; 0 disables timeout (env: AGENT_TIMEOUT_SECONDS, default: 300).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=os.getenv("POLL_ONCE", "").lower() in {"1", "true", "yes"},
        help="Run a single poll and exit (env: POLL_ONCE=1). Useful for tests/cron.",
    )
    parser.add_argument(
        "--max-polls",
        type=int,
        default=_env_int("MAX_POLLS", 0),
        help="Maximum number of polls before exiting; 0 means unlimited (env: MAX_POLLS).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging level (env: LOG_LEVEL, default: INFO).",
    )
    return parser.parse_args(argv)


class Config:
    def __init__(
        self,
        alert_url: str,
        interval: float,
        timeout: float,
        agent_command: str = "",
        once: bool = False,
        max_polls: int = 0,
        agent_timeout: float = 300.0,
    ) -> None:
        self.alert_url = alert_url
        self.interval = max(0.0, float(interval))
        self.timeout = float(timeout)
        self.agent_command = agent_command
        self.once = once
        self.max_polls = int(max_polls)
        self.agent_timeout = max(0.0, float(agent_timeout))


def build_config(args: argparse.Namespace | None = None) -> Config:
    args = args or parse_args()
    return Config(
        alert_url=args.alert_url,
        interval=args.interval,
        timeout=args.timeout,
        agent_command=args.agent_command,
        once=args.once,
        max_polls=args.max_polls,
        agent_timeout=args.agent_timeout,
    )


def fetch_alerts(url: str, timeout: float, headers: Mapping[str, str] | None = None) -> list[Alert] | dict[str, Any]:
    """Fetch alert payload from an HTTP/HTTPS endpoint returning JSON.

    Network, validation, and decode errors are raised so callers can handle them gracefully.
    """
    parsed = parse.urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Unsupported alert URL (expected http/https URL): {url!r}")
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = request.Request(url, headers=req_headers, method="GET")
    with request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset)
    if not body.strip():
        return []
    return json.loads(body)


def _as_alert_list(payload: Any) -> list[Alert]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("status"), str) and payload["status"].lower() == "error":
        error_type = payload.get("errorType") or "unknown"
        error_msg = payload.get("error") or "unknown error"
        raise ValueError(f"Alert API returned error status ({error_type}): {error_msg}")
    # Prometheus: {"status":"success","data":{"alerts":[...]}}
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("alerts", "result", "items"):
            if isinstance(data.get(key), list):
                return [item for item in data[key] if isinstance(item, dict)]
        if isinstance(data.get("rules"), list):
            alerts: list[Alert] = []
            for group in data["rules"]:
                if not isinstance(group, dict):
                    continue
                for rule in group.get("rules", []) if isinstance(group.get("rules"), list) else []:
                    if not isinstance(rule, dict):
                        continue
                    for alert in rule.get("alerts", []) if isinstance(rule.get("alerts"), list) else []:
                        if isinstance(alert, dict):
                            alerts.append({**alert, "rule": rule.get("name", alert.get("rule"))})
            return alerts
    # Alertmanager/Grafana/common: {"alerts":[...]}, {"instances":[...]}, {"items":[...]}
    for key in ("alerts", "instances", "items"):
        if isinstance(payload.get(key), list):
            return [item for item in payload[key] if isinstance(item, dict)]
    # Single alert object
    if "state" in payload or "status" in payload or "labels" in payload or "annotations" in payload:
        return [payload]
    return []


def _is_firing(alert: Alert) -> bool:
    # Prometheus Alertmanager API: status.state == "active" / "firing"
    status = alert.get("status")
    if isinstance(status, str) and status.lower() in {"firing", "active", "alerting"}:
        return True
    if isinstance(status, dict):
        state = status.get("state")
        if isinstance(state, str) and state.lower() in {"firing", "active", "alerting"}:
            return True
    # Grafana/Prometheus rule alerts: state == "firing"/"alerting"
    state = alert.get("state")
    if isinstance(state, str) and state.lower() in {"firing", "active", "alerting"}:
        return True
    # Some APIs use active=true or firing=true flags
    if alert.get("active") is True or alert.get("firing") is True:
        return True
    return False


def extract_active_alerts(payload: list[Alert] | dict[str, Any]) -> list[Alert]:
    """Return alert objects that are active/firing, normalized with extracted details."""
    alerts = _as_alert_list(payload)
    active: list[Alert] = []
    for alert in alerts:
        if not _is_firing(alert):
            continue
        labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
        annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
        status = alert.get("status")
        status_state = status.get("state") if isinstance(status, dict) else status
        name = (
            labels.get("alertname")
            or alert.get("alertname")
            or alert.get("name")
            or alert.get("title")
            or "unknown-alert"
        )
        details: Alert = {
            "name": name,
            "state": status_state or alert.get("state") or "firing",
            "severity": labels.get("severity") or alert.get("severity"),
            "service": labels.get("service") or alert.get("service"),
            "environment": labels.get("environment") or alert.get("environment"),
            "deployed_version": labels.get("deployed_version") or alert.get("deployed_version"),
            "summary": annotations.get("summary") or alert.get("summary"),
            "description": annotations.get("description") or alert.get("description"),
            "starts_at": alert.get("startsAt") or alert.get("activeAt") or alert.get("starts_at"),
            "ends_at": alert.get("endsAt") or alert.get("ends_at"),
            "generator_url": alert.get("generatorURL") or alert.get("generator_url"),
            "fingerprint": alert.get("fingerprint"),
            "labels": labels,
            "annotations": annotations,
            "raw": alert,
        }
        active.append(details)
    return active


def _render_command_argv(
    tokens: Sequence[str],
    *,
    alert_json: str,
    alert_file: str | None = None,
) -> list[str]:
    replacements = {"{alert_json}": alert_json}
    if alert_file is not None:
        replacements["{alert_file}"] = alert_file
    pattern = re.compile("|".join(re.escape(key) for key in replacements))
    return [pattern.sub(lambda match: replacements[match.group(0)], token) for token in tokens]


def default_agent_invoker(alert: Alert, config: Config) -> subprocess.CompletedProcess[str] | None:
    """Invoke a headless coding agent runner for a firing alert.

    If `config.agent_command` is set, it is split with `shlex.split` and executed with
    `shell=False`, substituting `{alert_json}` and `{alert_file}` safely per token.
    Without a command, the alert is logged so the polling service stays safe in dry runs.
    """
    alert_json = json.dumps(alert, sort_keys=True)
    if not config.agent_command or not config.agent_command.strip():
        logger.warning(
            "Firing alert detected but no AGENT_COMMAND configured: %s",
            json.dumps({k: v for k, v in alert.items() if k != "raw"}, sort_keys=True),
        )
        return None

    tokens = shlex.split(config.agent_command)
    if not tokens:
        logger.warning(
            "Firing alert detected but AGENT_COMMAND produced no tokens: %s",
            json.dumps({k: v for k, v in alert.items() if k != "raw"}, sort_keys=True),
        )
        return None

    uses_alert_file = any("{alert_file}" in token for token in tokens)
    alert_file_path: str | None = None
    timeout = config.agent_timeout if config.agent_timeout > 0 else None

    logger.info("Invoking agent for alert %s", alert.get("name"))
    try:
        if uses_alert_file:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                encoding="utf-8",
                delete=False,
            ) as tmp:
                tmp.write(alert_json)
                alert_file_path = tmp.name

        argv = _render_command_argv(tokens, alert_json=alert_json, alert_file=alert_file_path)
        result = subprocess.run(
            argv,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("Agent command timed out after %ss for alert %s", exc.timeout, alert.get("name"))
        raise
    except OSError as exc:
        logger.exception("Failed to invoke agent command for alert %s: %s", alert.get("name"), exc)
        raise
    finally:
        if alert_file_path is not None:
            try:
                os.unlink(alert_file_path)
            except FileNotFoundError:
                pass

    if result.returncode != 0:
        logger.error(
            "Agent command failed for alert %s with exit code %s; stdout=%r stderr=%r",
            alert.get("name"),
            result.returncode,
            result.stdout,
            result.stderr,
        )
        raise subprocess.CalledProcessError(
            result.returncode,
            argv,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def _alert_dedupe_key(alert: Alert) -> str:
    return str(
        alert.get("fingerprint")
        or json.dumps(
            {
                "name": alert.get("name"),
                "labels": alert.get("labels", {}),
                "starts_at": alert.get("starts_at"),
            },
            sort_keys=True,
        )
    )


def poll_once(
    config: Config,
    *,
    fetcher: FetchAlerts = fetch_alerts,
    invoker: InvokeAgent = default_agent_invoker,
    dedupe: set[str] | None = None,
) -> list[Alert]:
    """Run one poll cycle. Returns alerts that were handled/invoked."""
    try:
        payload = fetcher(config.alert_url, config.timeout, {})
        active_alerts = extract_active_alerts(payload)
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        logger.error("Alert poll failed (%s): %s", config.alert_url, exc)
        return []
    except Exception:
        logger.exception("Unexpected error while polling alerts")
        return []

    if dedupe is not None:
        active_keys = {_alert_dedupe_key(alert) for alert in active_alerts}
        dedupe.intersection_update(active_keys)

    if not active_alerts:
        logger.info("No active/firing alerts")
        return []

    handled: list[Alert] = []
    for alert in active_alerts:
        key = _alert_dedupe_key(alert)
        if dedupe is not None and key in dedupe:
            logger.debug("Skipping already-handled alert %s", alert.get("name"))
            continue
        logger.info(
            "Active alert: name=%s severity=%s service=%s environment=%s",
            alert.get("name"),
            alert.get("severity"),
            alert.get("service"),
            alert.get("environment"),
        )
        try:
            invoker(alert, config)
        except Exception:
            logger.exception("Agent invocation failed for alert %s", alert.get("name"))
            continue
        if dedupe is not None:
            dedupe.add(key)
        handled.append(alert)
    return handled


def run_loop(
    config: Config,
    *,
    fetcher: FetchAlerts = fetch_alerts,
    invoker: InvokeAgent = default_agent_invoker,
    sleep_fn: SleepFn = time.sleep,
) -> int:
    """Poll continuously until once/max-polls/interrupt. Returns poll count."""
    dedupe: set[str] = set()
    polls = 0
    logger.info(
        "Starting on-call alert poller url=%s interval=%ss once=%s",
        config.alert_url,
        config.interval,
        config.once,
    )
    while True:
        poll_once(config, fetcher=fetcher, invoker=invoker, dedupe=dedupe)
        polls += 1
        if config.once or (config.max_polls and polls >= config.max_polls):
            return polls
        try:
            sleep_fn(config.interval)
        except KeyboardInterrupt:
            logger.info("Interrupted, stopping poller")
            return polls


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    config = build_config(args)
    try:
        run_loop(config)
    except KeyboardInterrupt:
        logger.info("Interrupted, exiting")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
