from __future__ import annotations

from types import SimpleNamespace

from openclaw_skins.cli import (
    decode_pairing_setup_code,
    discover_gateway_auth,
    discover_gateway_token,
    parse_dashboard_output,
    parse_gateway_status_output,
    resolve_cli_invocation,
    split_cli_command,
)
from openclaw_skins.models import AppSettings, GatewayAuthDiscovery


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


def test_resolve_cli_invocation_uses_windows_cmd_shim(monkeypatch) -> None:
    monkeypatch.setattr("openclaw_skins.cli.os.name", "nt")

    def fake_which(candidate: str) -> str | None:
        if candidate == "openclaw.cmd":
            return r"C:\Users\juan\AppData\Roaming\npm\openclaw.cmd"
        return None

    monkeypatch.setattr("openclaw_skins.cli.shutil.which", fake_which)

    program, args = resolve_cli_invocation("openclaw")

    assert program.lower().endswith("cmd.exe")
    assert args == ["/c", r"C:\Users\juan\AppData\Roaming\npm\openclaw.cmd"]


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

    def fake_run(args, **_kwargs):
        if args[-3:] == ["config", "get", "gateway.auth.token"]:
            return SimpleNamespace(returncode=0, stdout="resolved-token\n", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr("openclaw_skins.cli.subprocess.run", fake_run)

    assert discover_gateway_token(settings) == "resolved-token"


def test_parse_dashboard_output_extracts_gateway_url_and_token() -> None:
    discovery = parse_dashboard_output(
        "Dashboard URL: http://127.0.0.1:18789/dashboard#token=abc123\nCopied to clipboard."
    )

    assert discovery == GatewayAuthDiscovery(
        gateway_url="ws://127.0.0.1:18789",
        gateway_token="abc123",
        bootstrap_token="",
    )


def test_decode_pairing_setup_code_reads_bootstrap_payload() -> None:
    payload = decode_pairing_setup_code(
        "eyJ1cmwiOiAid3M6Ly8xMjcuMC4wLjE6MTg3ODkiLCAiYm9vdHN0cmFwVG9rZW4iOiAiYm9vdHN0cmFwLTEyMyJ9"
    )

    assert payload == {"url": "ws://127.0.0.1:18789", "bootstrapToken": "bootstrap-123"}


def test_discover_gateway_auth_uses_dashboard_url_and_bootstrap_fallback(monkeypatch) -> None:
    settings = AppSettings(gateway_token="", gateway_url="ws://127.0.0.1:18789", cli_command="openclaw")

    def fake_run(args, **_kwargs):
        if args[-3:] == ["config", "get", "gateway.auth.token"]:
            return SimpleNamespace(returncode=0, stdout="__OPENCLAW_REDACTED__\n", stderr="")
        if args[-2:] == ["dashboard", "--no-open"]:
            return SimpleNamespace(
                returncode=0,
                stdout="Dashboard URL: http://127.0.0.1:18790/#token=real-token\n",
                stderr="",
            )
        if args[-4:] == ["qr", "--setup-code-only", "--url", "ws://127.0.0.1:18790"]:
            return SimpleNamespace(
                returncode=0,
                stdout="eyJ1cmwiOiAid3M6Ly8xMjcuMC4wLjE6MTg3OTAiLCAiYm9vdHN0cmFwVG9rZW4iOiAiYm9vdHN0cmFwLTEyMyJ9\n",
                stderr="",
            )
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr("openclaw_skins.cli.subprocess.run", fake_run)

    discovery = discover_gateway_auth(settings)

    assert discovery == GatewayAuthDiscovery(
        gateway_url="ws://127.0.0.1:18790",
        gateway_token="real-token",
        bootstrap_token="",
    )
