from __future__ import annotations

from openclaw_skins.cli import parse_gateway_status_output, split_cli_command


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
