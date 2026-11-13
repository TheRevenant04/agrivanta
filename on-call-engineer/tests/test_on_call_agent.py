import json
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure on-call-engineer/ is importable when running `uv run pytest on-call-engineer/tests`
PACKAGE_DIR = Path(__file__).resolve().parents[1]
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

import on_call_agent as poller  # noqa: E402


def test_parse_args_defaults_and_env(monkeypatch):
    monkeypatch.setenv("ALERT_API_URL", "http://alerts.example/api/v1/alerts")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "45")
    monkeypatch.setenv("ALERT_API_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("AGENT_COMMAND", "echo {alert_json}")
    monkeypatch.setenv("POLL_ONCE", "1")
    monkeypatch.setenv("MAX_POLLS", "3")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    args = poller.parse_args([])

    assert args.alert_url == "http://alerts.example/api/v1/alerts"
    assert args.interval == 45.0
    assert args.timeout == 7.0
    assert args.agent_command == "echo {alert_json}"
    assert args.once is True
    assert args.max_polls == 3
    assert args.log_level == "DEBUG"


def test_parse_args_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("ALERT_API_URL", "http://env")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "60")

    args = poller.parse_args([
        "--alert-url", "http://cli",
        "--interval", "15",
        "--timeout", "3",
        "--agent-command", "runner {alert_json}",
        "--max-polls", "2",
    ])

    assert args.alert_url == "http://cli"
    assert args.interval == 15.0
    assert args.timeout == 3.0
    assert args.agent_command == "runner {alert_json}"
    assert args.max_polls == 2
    assert args.once is False


def test_extract_active_alerts_prometheus_payload():
    payload = {
        "status": "success",
        "data": {
            "alerts": [
                {
                    "labels": {
                        "alertname": "HighErrorRate",
                        "severity": "critical",
                        "service": "agrivanta-backend",
                        "environment": "prod",
                    },
                    "annotations": {"summary": "Errors high", "description": "5xx spike"},
                    "state": "firing",
                    "activeAt": "2026-11-13T10:00:00Z",
                    "fingerprint": "abc123",
                },
                {
                    "labels": {"alertname": "ResolvedThing"},
                    "state": "inactive",
                },
            ]
        },
    }

    active = poller.extract_active_alerts(payload)

    assert len(active) == 1
    alert = active[0]
    assert alert["name"] == "HighErrorRate"
    assert alert["state"] == "firing"
    assert alert["severity"] == "critical"
    assert alert["service"] == "agrivanta-backend"
    assert alert["environment"] == "prod"
    assert alert["summary"] == "Errors high"
    assert alert["description"] == "5xx spike"
    assert alert["starts_at"] == "2026-11-13T10:00:00Z"
    assert alert["fingerprint"] == "abc123"
    assert alert["labels"]["alertname"] == "HighErrorRate"


def test_extract_active_alerts_alertmanager_style():
    payload = {
        "alerts": [
            {
                "status": {"state": "active"},
                "labels": {"alertname": "DiskFull", "severity": "warning"},
                "annotations": {"summary": "Disk almost full"},
                "startsAt": "2026-11-13T11:00:00Z",
            },
            {
                "status": {"state": "suppressed"},
                "labels": {"alertname": "IgnoreMe"},
            },
        ]
    }

    active = poller.extract_active_alerts(payload)

    assert [a["name"] for a in active] == ["DiskFull"]
    assert active[0]["state"] == "active"
    assert active[0]["severity"] == "warning"


def test_poll_once_invokes_agent_for_each_new_firing_alert():
    config = poller.Config("http://example/alerts", interval=60, timeout=5, agent_command="echo {alert_json}")
    payload = {
        "data": {
            "alerts": [
                {"labels": {"alertname": "A"}, "state": "firing", "fingerprint": "fp-a"},
                {"labels": {"alertname": "B"}, "state": "firing", "fingerprint": "fp-b"},
                {"labels": {"alertname": "C"}, "state": "inactive", "fingerprint": "fp-c"},
            ]
        }
    }
    invoked = []

    def fake_fetch(url, timeout, headers):
        assert url == config.alert_url
        assert timeout == config.timeout
        return payload

    def fake_invoke(alert, cfg):
        assert cfg is config
        invoked.append(alert["name"])
        return "ok"

    handled = poller.poll_once(config, fetcher=fake_fetch, invoker=fake_invoke, dedupe=set())

    assert [a["name"] for a in handled] == ["A", "B"]
    assert invoked == ["A", "B"]


def test_poll_once_deduplicates_alerts_across_polls():
    config = poller.Config("http://example/alerts", interval=60, timeout=5)
    payload = {"data": {"alerts": [{"labels": {"alertname": "Same"}, "state": "firing", "fingerprint": "same"}]}}
    invoked = []
    dedupe = set()

    first = poller.poll_once(config, fetcher=lambda *_: payload, invoker=lambda a, c: invoked.append(a["name"]), dedupe=dedupe)
    second = poller.poll_once(config, fetcher=lambda *_: payload, invoker=lambda a, c: invoked.append(a["name"]), dedupe=dedupe)

    assert [a["name"] for a in first] == ["Same"]
    assert second == []
    assert invoked == ["Same"]


def test_poll_once_handles_fetch_errors_gracefully(caplog):
    config = poller.Config("http://example/alerts", interval=60, timeout=5)
    invoked = []

    def boom(*_args, **_kwargs):
        raise TimeoutError("timed out")

    with caplog.at_level("ERROR"):
        handled = poller.poll_once(config, fetcher=boom, invoker=lambda a, c: invoked.append(a))

    assert handled == []
    assert invoked == []
    assert any("Alert poll failed" in rec.message for rec in caplog.records)


def test_poll_once_handles_malformed_json_error_gracefully():
    config = poller.Config("http://example/alerts", interval=60, timeout=5)

    def bad_json(*_args, **_kwargs):
        raise json.JSONDecodeError("bad", "{", 1)

    handled = poller.poll_once(config, fetcher=bad_json, invoker=lambda *_: None)
    assert handled == []


def test_poll_once_continues_when_invoker_raises(caplog):
    config = poller.Config("http://example/alerts", interval=60, timeout=5)
    payload = {
        "data": {
            "alerts": [
                {"labels": {"alertname": "First"}, "state": "firing", "fingerprint": "1"},
                {"labels": {"alertname": "Second"}, "state": "firing", "fingerprint": "2"},
            ]
        }
    }

    def flaky_invoker(alert, _cfg):
        if alert["name"] == "First":
            raise RuntimeError("runner unavailable")
        return "ok"

    with caplog.at_level("ERROR"):
        handled = poller.poll_once(config, fetcher=lambda *_: payload, invoker=flaky_invoker, dedupe=set())

    assert [a["name"] for a in handled] == ["Second"]
    assert any("Agent invocation failed" in rec.message for rec in caplog.records)


def test_default_agent_invoker_runs_configured_command(monkeypatch):
    config = poller.Config("http://example/alerts", 60, 5, agent_command="agent-run --payload {alert_json}")
    calls = {}

    def fake_run(cmd, shell, check, capture_output, text):
        calls["cmd"] = cmd
        calls["shell"] = shell
        calls["check"] = check
        calls["capture_output"] = capture_output
        calls["text"] = text
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(poller.subprocess, "run", fake_run)
    alert = {"name": "X", "state": "firing", "labels": {"alertname": "X"}}

    result = poller.default_agent_invoker(alert, config)

    assert isinstance(result, subprocess.CompletedProcess)
    assert calls["shell"] is True
    assert calls["check"] is False
    assert "agent-run --payload" in calls["cmd"]


def test_default_agent_invoker_without_command_logs_and_skips(caplog):
    config = poller.Config("http://example/alerts", 60, 5, agent_command="")
    with caplog.at_level("WARNING"):
        result = poller.default_agent_invoker({"name": "NoRunner", "labels": {}, "annotations": {}}, config)
    assert result is None
    assert any("no AGENT_COMMAND configured" in rec.message for rec in caplog.records)


def test_run_loop_calls_poll_once_and_sleeps(monkeypatch):
    config = poller.Config("http://example/alerts", interval=30, timeout=5, max_polls=2)
    calls = {"poll": 0, "sleep": []}

    def fake_poll_once(cfg, fetcher=None, invoker=None, dedupe=None):
        calls["poll"] += 1
        return []

    monkeypatch.setattr(poller, "poll_once", fake_poll_once)

    count = poller.run_loop(config, sleep_fn=lambda s: calls["sleep"].append(s))

    assert count == 2
    assert calls["poll"] == 2
    assert calls["sleep"] == [30]


def test_run_loop_once_mode_no_sleep(monkeypatch):
    config = poller.Config("http://example/alerts", interval=60, timeout=5, once=True)
    calls = {"poll": 0, "sleep": 0}

    monkeypatch.setattr(poller, "poll_once", lambda *a, **k: calls.__setitem__("poll", calls["poll"] + 1) or [])

    count = poller.run_loop(config, sleep_fn=lambda _: calls.__setitem__("sleep", calls["sleep"] + 1))

    assert count == 1
    assert calls["poll"] == 1
    assert calls["sleep"] == 0
