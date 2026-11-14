import json
import subprocess
import sys
from pathlib import Path
from urllib import error

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
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("POLL_ONCE", "1")
    monkeypatch.setenv("MAX_POLLS", "3")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    args = poller.parse_args([])

    assert args.alert_url == "http://alerts.example/api/v1/alerts"
    assert args.interval == 45.0
    assert args.timeout == 7.0
    assert args.agent_command == "echo {alert_json}"
    assert args.agent_timeout == 120.0
    assert args.once is True
    assert args.max_polls == 3
    assert args.log_level == "DEBUG"


def test_parse_args_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("ALERT_API_URL", "http://env")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "300")

    args = poller.parse_args([
        "--alert-url", "http://cli",
        "--interval", "15",
        "--timeout", "3",
        "--agent-command", "runner {alert_json}",
        "--agent-timeout", "42",
        "--max-polls", "2",
    ])

    assert args.alert_url == "http://cli"
    assert args.interval == 15.0
    assert args.timeout == 3.0
    assert args.agent_command == "runner {alert_json}"
    assert args.agent_timeout == 42.0
    assert args.max_polls == 2
    assert args.once is False


def test_fetch_alerts_success_and_headers(monkeypatch):
    captured = {}

    class FakeHeaders:
        @staticmethod
        def get_content_charset():
            return "utf-8"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def read():
            return json.dumps({"status": "success", "data": {"alerts": [{"state": "firing"}]}}).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(poller.request, "urlopen", fake_urlopen)

    result = poller.fetch_alerts("https://alerts.example.com/api/v1/alerts", 8.5, {"Authorization": "Bearer tok"})

    assert result == {"status": "success", "data": {"alerts": [{"state": "firing"}]}}
    assert captured["url"] == "https://alerts.example.com/api/v1/alerts"
    assert captured["method"] == "GET"
    assert captured["timeout"] == 8.5
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["headers"]["Authorization"] == "Bearer tok"


def test_fetch_alerts_empty_body_returns_empty_list(monkeypatch):
    class FakeHeaders:
        @staticmethod
        def get_content_charset():
            return None

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def read():
            return b"   \n"

    monkeypatch.setattr(poller.request, "urlopen", lambda req, timeout: FakeResponse())

    assert poller.fetch_alerts("http://localhost:9090/alerts", 5.0) == []


@pytest.mark.parametrize(
    "bad_url",
    [
        "file:///etc/passwd",
        "ftp://alerts.example.com/alerts",
        "javascript:alert(1)",
        "/relative/path",
        "http:///missing-host",
        "",
    ],
)
def test_fetch_alerts_rejects_disallowed_url_schemes(monkeypatch, bad_url):
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("urlopen must not be called for invalid URLs")

    monkeypatch.setattr(poller.request, "urlopen", fail_if_called)

    with pytest.raises(ValueError, match="Unsupported alert URL"):
        poller.fetch_alerts(bad_url, 5.0)

    assert called is False


def test_fetch_alerts_propagates_network_errors(monkeypatch):
    def fake_urlopen(_req, timeout):
        raise error.URLError("connection refused")

    monkeypatch.setattr(poller.request, "urlopen", fake_urlopen)

    with pytest.raises(error.URLError):
        poller.fetch_alerts("http://localhost:9090/alerts", 5.0)


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


def test_extract_active_alerts_data_rules_shape():
    payload = {
        "status": "success",
        "data": {
            "rules": [
                {
                    "name": "backend-group",
                    "rules": [
                        {
                            "name": "HighLatency",
                            "alerts": [
                                {"labels": {"alertname": "HighLatency"}, "state": "firing"},
                                {"labels": {"alertname": "CoolDown"}, "state": "pending"},
                            ],
                        },
                        {
                            "name": "EmptyRule",
                            "alerts": [],
                        },
                    ],
                }
            ]
        },
    }

    active = poller.extract_active_alerts(payload)

    assert len(active) == 1
    assert active[0]["name"] == "HighLatency"
    assert active[0]["raw"]["rule"] == "HighLatency"


def test_extract_active_alerts_data_rules_all_resolved_returns_empty():
    payload = {
        "status": "success",
        "data": {
            "rules": [
                {"name": "g1", "rules": [{"name": "r1", "alerts": []}]},
            ]
        },
    }

    assert poller._as_alert_list(payload) == []
    assert poller.extract_active_alerts(payload) == []


def test_extract_active_alerts_top_level_list_and_single_object():
    list_payload = [
        {"name": "ListFiring", "state": "alerting"},
        {"name": "ListResolved", "state": "ok"},
    ]
    assert [a["name"] for a in poller.extract_active_alerts(list_payload)] == ["ListFiring"]

    single_payload = {
        "labels": {"alertname": "SoloAlert", "severity": "critical"},
        "annotations": {"summary": "Solo failure"},
        "state": "firing",
    }
    single_active = poller.extract_active_alerts(single_payload)
    assert len(single_active) == 1
    assert single_active[0]["name"] == "SoloAlert"
    assert single_active[0]["summary"] == "Solo failure"


def test_extract_active_alerts_boolean_firing_and_active_flags():
    payload = [
        {"name": "BoolFiring", "firing": True},
        {"name": "BoolActive", "active": True},
        {"name": "BoolFalse", "firing": False, "active": False},
    ]

    active = poller.extract_active_alerts(payload)

    assert [a["name"] for a in active] == ["BoolFiring", "BoolActive"]
    assert all(a["state"] == "firing" for a in active)


def test_extract_active_alerts_prometheus_error_payload_raises_and_poll_once_logs(caplog):
    payload = {
        "status": "error",
        "errorType": "bad_data",
        "error": "invalid parameter",
    }

    with pytest.raises(ValueError, match="Alert API returned error status"):
        poller.extract_active_alerts(payload)

    config = poller.Config("http://example/alerts", interval=60, timeout=5)
    dedupe = {"existing-fp"}

    with caplog.at_level("ERROR"):
        handled = poller.poll_once(config, fetcher=lambda *_: payload, invoker=lambda *_: None, dedupe=dedupe)

    assert handled == []
    assert dedupe == {"existing-fp"}
    assert any("Alert poll failed" in rec.message for rec in caplog.records)


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


def test_poll_once_deduplicates_active_alerts_and_evicts_resolved():
    config = poller.Config("http://example/alerts", interval=60, timeout=5)
    firing_payload = {"data": {"alerts": [{"labels": {"alertname": "Same"}, "state": "firing", "fingerprint": "same"}]}}
    resolved_payload = {"data": {"alerts": [{"labels": {"alertname": "Same"}, "state": "inactive", "fingerprint": "same"}]}}
    invoked = []
    dedupe = set()

    first = poller.poll_once(config, fetcher=lambda *_: firing_payload, invoker=lambda a, c: invoked.append(a["name"]), dedupe=dedupe)
    second = poller.poll_once(config, fetcher=lambda *_: firing_payload, invoker=lambda a, c: invoked.append(a["name"]), dedupe=dedupe)
    third = poller.poll_once(config, fetcher=lambda *_: resolved_payload, invoker=lambda a, c: invoked.append(a["name"]), dedupe=dedupe)
    fourth = poller.poll_once(config, fetcher=lambda *_: firing_payload, invoker=lambda a, c: invoked.append(a["name"]), dedupe=dedupe)

    assert [a["name"] for a in first] == ["Same"]
    assert second == []
    assert third == []
    assert [a["name"] for a in fourth] == ["Same"]
    assert invoked == ["Same", "Same"]


def test_poll_once_retries_failed_invoker_and_dedupes_after_success(caplog):
    config = poller.Config("http://example/alerts", interval=60, timeout=5)
    payload = {"data": {"alerts": [{"labels": {"alertname": "Flaky"}, "state": "firing", "fingerprint": "fp-flaky"}]}}
    dedupe = set()
    attempts = 0

    def flaky_invoker(_alert, _cfg):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise subprocess.CalledProcessError(1, ["runner"], stderr="boom")
        return subprocess.CompletedProcess(["runner"], 0)

    with caplog.at_level("ERROR"):
        first = poller.poll_once(config, fetcher=lambda *_: payload, invoker=flaky_invoker, dedupe=dedupe)

    assert first == []
    assert dedupe == set()
    assert any("Agent invocation failed" in rec.message for rec in caplog.records)

    second = poller.poll_once(config, fetcher=lambda *_: payload, invoker=flaky_invoker, dedupe=dedupe)
    third = poller.poll_once(config, fetcher=lambda *_: payload, invoker=flaky_invoker, dedupe=dedupe)

    assert [a["name"] for a in second] == ["Flaky"]
    assert dedupe == {"fp-flaky"}
    assert third == []
    assert attempts == 2


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
    dedupe = set()

    def flaky_invoker(alert, _cfg):
        if alert["name"] == "First":
            raise RuntimeError("runner unavailable")
        return "ok"

    with caplog.at_level("ERROR"):
        handled = poller.poll_once(config, fetcher=lambda *_: payload, invoker=flaky_invoker, dedupe=dedupe)

    assert [a["name"] for a in handled] == ["Second"]
    assert dedupe == {"2"}
    assert any("Agent invocation failed" in rec.message for rec in caplog.records)


def test_default_agent_invoker_runs_configured_command_with_shell_false_and_safe_tokens(monkeypatch):
    config = poller.Config(
        "http://example/alerts",
        60,
        5,
        agent_command='agent-run --tag {literal_brace} --payload "Alert: {alert_json}"',
        agent_timeout=45.0,
    )
    calls = {}

    def fake_run(cmd, shell, check, capture_output, text, timeout):
        calls["cmd"] = cmd
        calls["shell"] = shell
        calls["check"] = check
        calls["capture_output"] = capture_output
        calls["text"] = text
        calls["timeout"] = timeout
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(poller.subprocess, "run", fake_run)
    alert = {
        "name": "X",
        "state": "firing",
        "summary": "$(touch /tmp/pwned); rm -rf / & calc {alert_file}",
        "labels": {"alertname": "X"},
    }

    result = poller.default_agent_invoker(alert, config)

    assert isinstance(result, subprocess.CompletedProcess)
    assert calls["shell"] is False
    assert calls["check"] is False
    assert calls["capture_output"] is True
    assert calls["text"] is True
    assert calls["timeout"] == 45.0
    assert isinstance(calls["cmd"], list)
    assert calls["cmd"][:4] == ["agent-run", "--tag", "{literal_brace}", "--payload"]
    expected_json = json.dumps(alert, sort_keys=True)
    assert calls["cmd"][4] == f"Alert: {expected_json}"


def test_default_agent_invoker_writes_and_cleans_up_alert_file(monkeypatch):
    config = poller.Config(
        "http://example/alerts",
        60,
        5,
        agent_command="agent-run --file {alert_file} --json {alert_json}",
    )
    seen = {}
    alert = {"name": "FileAlert", "state": "firing", "summary": "Literal {alert_file} in payload"}

    def fake_run(cmd, shell, check, capture_output, text, timeout):
        assert shell is False
        file_arg = cmd[2]
        seen["path"] = Path(file_arg)
        seen["exists_during_run"] = seen["path"].exists()
        seen["content_during_run"] = json.loads(seen["path"].read_text(encoding="utf-8"))
        seen["json_arg"] = cmd[4]
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(poller.subprocess, "run", fake_run)

    result = poller.default_agent_invoker(alert, config)

    assert result is not None
    assert seen["path"].suffix == ".json"
    assert seen["exists_during_run"] is True
    assert seen["content_during_run"] == alert
    assert seen["json_arg"] == json.dumps(alert, sort_keys=True)
    assert not seen["path"].exists()


def test_default_agent_invoker_cleans_up_alert_file_on_failure(monkeypatch):
    config = poller.Config("http://example/alerts", 60, 5, agent_command="agent-run {alert_file}")
    seen = {}

    def fake_run(cmd, **_kwargs):
        seen["path"] = Path(cmd[1])
        assert seen["path"].exists()
        raise OSError("missing executable")

    monkeypatch.setattr(poller.subprocess, "run", fake_run)

    with pytest.raises(OSError, match="missing executable"):
        poller.default_agent_invoker({"name": "FailFile"}, config)

    assert not seen["path"].exists()


def test_default_agent_invoker_raises_on_nonzero_exit_code(monkeypatch, caplog):
    config = poller.Config("http://example/alerts", 60, 5, agent_command="agent-run {alert_json}")

    def fake_run(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, 2, stdout="partial out", stderr="fatal error")

    monkeypatch.setattr(poller.subprocess, "run", fake_run)

    with caplog.at_level("ERROR"):
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            poller.default_agent_invoker({"name": "ExitTwo"}, config)

    assert exc_info.value.returncode == 2
    assert any(
        "exit code 2" in rec.message and "partial out" in rec.message and "fatal error" in rec.message
        for rec in caplog.records
    )


def test_default_agent_invoker_raises_on_oserror(monkeypatch, caplog):
    config = poller.Config("http://example/alerts", 60, 5, agent_command="nonexistent-bin {alert_json}")

    def fake_run(*_args, **_kwargs):
        raise OSError("No such file or directory")

    monkeypatch.setattr(poller.subprocess, "run", fake_run)

    with caplog.at_level("ERROR"):
        with pytest.raises(OSError, match="No such file"):
            poller.default_agent_invoker({"name": "MissingBin"}, config)

    assert any("Failed to invoke agent command" in rec.message for rec in caplog.records)


def test_default_agent_invoker_raises_on_timeout_expired(monkeypatch, caplog):
    config = poller.Config("http://example/alerts", 60, 5, agent_command="slow-bin {alert_json}", agent_timeout=1.5)

    def fake_run(cmd, **_kwargs):
        raise subprocess.TimeoutExpired(cmd, 1.5)

    monkeypatch.setattr(poller.subprocess, "run", fake_run)

    with caplog.at_level("ERROR"):
        with pytest.raises(subprocess.TimeoutExpired):
            poller.default_agent_invoker({"name": "SlowBin"}, config)

    assert any("timed out" in rec.message for rec in caplog.records)


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


def test_main_cli_entrypoint_runs_once_and_handles_interrupt(monkeypatch):
    captured = {}

    def fake_run_loop(cfg):
        captured["config"] = cfg
        return 1

    monkeypatch.setattr(poller, "run_loop", fake_run_loop)

    exit_code = poller.main([
        "--alert-url", "https://alerts.example/api/v1/alerts",
        "--interval", "15",
        "--timeout", "4",
        "--agent-command", "runner {alert_file}",
        "--agent-timeout", "90",
        "--once",
        "--log-level", "WARNING",
    ])

    assert exit_code == 0
    assert captured["config"].alert_url == "https://alerts.example/api/v1/alerts"
    assert captured["config"].interval == 15.0
    assert captured["config"].timeout == 4.0
    assert captured["config"].agent_command == "runner {alert_file}"
    assert captured["config"].agent_timeout == 90.0
    assert captured["config"].once is True

    monkeypatch.setattr(poller, "run_loop", lambda _cfg: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert poller.main(["--once"]) == 0
