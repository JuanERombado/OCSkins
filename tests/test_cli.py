from __future__ import annotations

from types import SimpleNamespace

from openclaw_skins.cli import discover_gateway_token, parse_gateway_status_output, split_cli_command
from openclaw_skins.models import AppSettings


MISSING_SERVICE_OUTPUT = """
Service: Scheduled Task (missing)
Runtime: stopped (ERROR: The system cannot find the file specified.)
Service unit not found.
Service not installed. Run: openclaw gateway install
""".strip()

RUNNING_SERVICE_OUTPUT = """
Service: Scheduled Task
Runtime: running (PID 1234)
Config (cli): C:\\Users\\jromb\\.openclaw\\openclaw.json
""".strip()

MISSING_COMMAND_OUTPUT = """
'openclaw' is not recognized as an internal or external command,
operable program or batch file.
""".strip()


def test_status_parser_marks_missing_service_as_non_restartable() -> None:
    status = parse_gateway_status_output(MISSING_SERVICE_OUTPUT)
    assert status.service_present is False
    assert status.can_restart is False
    assert "not installed" in status.summary.lower()
    assert "install" in status.disabled_reason.lower()


def test_status_parser_marks_running_service_as_restartable() -> None:
    status = parse_gateway_status_output(RUNNING_SERVICE_OUTPUT)
    assert status.service_present is True
    assert status.can_restart is True
    assert "running" in status.summary.lower()


def test_split_cli_command_supports_wrapped_commands() -> None:
    program, args = split_cli_command("wsl openclaw")
    assert program == "wsl"
    assert args == ["openclaw"]


def test_status_parser_marks_missing_cli_as_unavailable() -> None:
    status = parse_gateway_status_output(MISSING_COMMAND_OUTPUT)
    assert status.service_present is False
    assert status.can_restart is False
    assert "cli is unavailable" in status.summary.lower()


def test_discover_gateway_token_prefers_explicit_settings_value() -> None:
    settings = AppSettings(gateway_token="stored-token")
    assert discover_gateway_token(settings) == "stored-token"


def test_discover_gateway_token_uses_cli_config_fallback(monkeypatch) -> None:
    settings = AppSettings(gateway_token="", cli_command="openclaw")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="resolved-token\n")

    monkeypatch.setattr("openclaw_skins.cli.subprocess.run", fake_run)

    assert discover_gateway_token(settings) == "resolved-token"
