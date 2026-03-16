from __future__ import annotations

import base64
import json
import os
import re
import shlex
import shutil
import subprocess
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, QProcess, Signal

from openclaw_skins.models import AppSettings, GatewayAuthDiscovery, GatewayServiceStatus


def split_cli_command(command: str) -> tuple[str, list[str]]:
    parts = shlex.split(command, posix=False)
    cleaned = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part for part in parts]
    if not cleaned:
        raise ValueError("cli command cannot be empty")
    return cleaned[0], cleaned[1:]


def resolve_cli_invocation(command: str) -> tuple[str, list[str]]:
    program, base_args = split_cli_command(command)
    if os.name != "nt":
        return program, base_args

    candidate_paths = [program]
    if not os.path.splitext(program)[1]:
        candidate_paths.extend([f"{program}.cmd", f"{program}.exe", f"{program}.ps1", f"{program}.bat"])

    resolved = ""
    for candidate in candidate_paths:
        found = shutil.which(candidate)
        if found:
            resolved = found
            break
    program = resolved or program
    suffix = os.path.splitext(program)[1].lower()
    if suffix == ".ps1":
        return "powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", program, *base_args]
    if suffix in {".cmd", ".bat"}:
        return os.environ.get("COMSPEC", "cmd.exe"), ["/c", program, *base_args]
    return program, base_args


def _sanitize_token(candidate: str) -> str:
    value = candidate.strip()
    if not value:
        return ""
    if value.startswith("${") and value.endswith("}"):
        return ""
    if value.lower() in {"null", "none", "undefined"}:
        return ""
    if "redacted" in value.lower():
        return ""
    return value


def _run_cli_command(
    settings: AppSettings,
    extra_args: list[str],
    timeout_seconds: float = 4.0,
) -> subprocess.CompletedProcess[str] | None:
    try:
        program, base_args = resolve_cli_invocation(settings.cli_command)
    except ValueError:
        return None

    try:
        return subprocess.run(
            [program, *base_args, *extra_args],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def parse_dashboard_output(output: str) -> GatewayAuthDiscovery:
    match = re.search(r"^Dashboard URL:\s*(.+)$", output, re.IGNORECASE | re.MULTILINE)
    if not match:
        return GatewayAuthDiscovery()
    dashboard_url = match.group(1).strip()
    try:
        parsed = urlparse(dashboard_url)
    except ValueError:
        return GatewayAuthDiscovery()
    scheme = parsed.scheme.lower()
    if scheme == "http":
        gateway_scheme = "ws"
    elif scheme == "https":
        gateway_scheme = "wss"
    elif scheme in {"ws", "wss"}:
        gateway_scheme = scheme
    else:
        return GatewayAuthDiscovery()
    if not parsed.hostname:
        return GatewayAuthDiscovery()
    port = f":{parsed.port}" if parsed.port else ""
    fragment_params = parse_qs(parsed.fragment, keep_blank_values=True)
    token = _sanitize_token(fragment_params.get("token", [""])[0])
    return GatewayAuthDiscovery(
        gateway_url=f"{gateway_scheme}://{parsed.hostname}{port}",
        gateway_token=token,
        bootstrap_token="",
    )


def decode_pairing_setup_code(setup_code: str) -> dict[str, str] | None:
    raw_code = setup_code.strip()
    if not raw_code:
        return None
    padded = raw_code + ("=" * ((4 - (len(raw_code) % 4)) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    url = payload.get("url")
    bootstrap_token = payload.get("bootstrapToken")
    if not isinstance(url, str) or not isinstance(bootstrap_token, str):
        return None
    if not url.strip() or not bootstrap_token.strip():
        return None
    return {"url": url.strip(), "bootstrapToken": bootstrap_token.strip()}


def discover_gateway_bootstrap_token(
    settings: AppSettings,
    gateway_url: str,
    timeout_seconds: float = 6.0,
) -> str:
    if not gateway_url.strip():
        return ""
    completed = _run_cli_command(
        settings,
        ["qr", "--setup-code-only", "--url", gateway_url.strip()],
        timeout_seconds=timeout_seconds,
    )
    if completed is None or completed.returncode != 0:
        return ""
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return ""
    payload = decode_pairing_setup_code(lines[-1])
    if payload is None:
        return ""
    return _sanitize_token(payload.get("bootstrapToken", ""))


def discover_gateway_auth(settings: AppSettings, timeout_seconds: float = 4.0) -> GatewayAuthDiscovery:
    resolved_url = settings.gateway_url.strip()
    explicit_token = _sanitize_token(settings.gateway_token)
    if explicit_token:
        return GatewayAuthDiscovery(gateway_url=resolved_url, gateway_token=explicit_token)

    for env_name in ("OPENCLAW_GATEWAY_TOKEN", "CLAWDBOT_GATEWAY_TOKEN"):
        env_value = _sanitize_token(os.environ.get(env_name, ""))
        if env_value:
            return GatewayAuthDiscovery(gateway_url=resolved_url, gateway_token=env_value)

    config_completed = _run_cli_command(
        settings,
        ["config", "get", "gateway.auth.token"],
        timeout_seconds=timeout_seconds,
    )
    if config_completed is not None and config_completed.returncode == 0:
        config_token = _sanitize_token(config_completed.stdout)
        if config_token:
            return GatewayAuthDiscovery(gateway_url=resolved_url, gateway_token=config_token)

    dashboard_completed = _run_cli_command(
        settings,
        ["dashboard", "--no-open"],
        timeout_seconds=timeout_seconds,
    )
    dashboard = GatewayAuthDiscovery(gateway_url=resolved_url)
    if dashboard_completed is not None and dashboard_completed.returncode == 0:
        dashboard = parse_dashboard_output(dashboard_completed.stdout)
        if dashboard.gateway_url:
            resolved_url = dashboard.gateway_url
        if dashboard.gateway_token:
            return GatewayAuthDiscovery(
                gateway_url=resolved_url,
                gateway_token=dashboard.gateway_token,
                bootstrap_token="",
            )

    bootstrap_token = discover_gateway_bootstrap_token(
        settings,
        resolved_url,
        timeout_seconds=max(timeout_seconds, 6.0),
    )
    return GatewayAuthDiscovery(
        gateway_url=resolved_url,
        gateway_token="",
        bootstrap_token=bootstrap_token,
    )


def discover_gateway_token(settings: AppSettings, timeout_seconds: float = 4.0) -> str:
    return discover_gateway_auth(settings, timeout_seconds=timeout_seconds).gateway_token


def parse_gateway_status_output(output: str) -> GatewayServiceStatus:
    text = output.strip()
    service_match = re.search(r"^Service:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    runtime_match = re.search(r"^Runtime:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    service_line = service_match.group(1).strip() if service_match else ""
    runtime_line = runtime_match.group(1).strip() if runtime_match else ""

    service_present = True
    if "(missing)" in service_line.lower():
        service_present = False
    if re.search(r"service unit not found", text, re.IGNORECASE):
        service_present = False
    if re.search(r"service not installed", text, re.IGNORECASE):
        service_present = False

    command_unavailable = False
    if re.search(r"not recognized as an internal or external command", text, re.IGNORECASE):
        command_unavailable = True
    if re.search(r"no such file or directory", text, re.IGNORECASE):
        command_unavailable = True

    if command_unavailable:
        service_present = False
        summary = "OpenClaw CLI is unavailable."
        detail_message = text or "The configured CLI command could not be executed."
        disabled_reason = "Gateway restart is unavailable until the OpenClaw CLI command works."
    elif service_present:
        summary = "Gateway service is available."
        detail_message = runtime_line or service_line or "Gateway service can be controlled from this app."
        disabled_reason = ""
    else:
        summary = "Gateway service is not installed."
        detail_message = "Install the managed OpenClaw gateway service before using restart from the skin."
        disabled_reason = "Gateway service is not installed. Run `openclaw gateway install` first."

    if runtime_line:
        if service_present:
            if runtime_line.lower().startswith("running"):
                summary = "Gateway service is running."
            elif runtime_line.lower().startswith("stopped"):
                summary = "Gateway service is stopped."
        detail_message = runtime_line

    return GatewayServiceStatus(
        service_present=service_present,
        can_restart=service_present and not command_unavailable,
        summary=summary,
        detail_message=detail_message,
        disabled_reason=disabled_reason,
        runtime_label=runtime_line,
        raw_output=text,
    )


class OpenClawCliBridge(QObject):
    service_status_changed = Signal(object)
    command_started = Signal(str)
    command_finished = Signal(str, bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._command_name: str | None = None
        self._last_output = ""
        self._process_error = ""

    def check_gateway_status(self, settings: AppSettings) -> bool:
        return self._start("status", settings, ["gateway", "status"])

    def restart_gateway(self, settings: AppSettings) -> bool:
        return self._start("restart", settings, ["gateway", "restart"])

    def discover_gateway_token(self, settings: AppSettings) -> str:
        return discover_gateway_token(settings)

    def discover_gateway_auth(self, settings: AppSettings) -> GatewayAuthDiscovery:
        return discover_gateway_auth(settings)

    def cancel(self) -> None:
        if self._process is not None:
            self._process.kill()
            self._process = None
            self._command_name = None

    def _start(self, name: str, settings: AppSettings, extra_args: list[str]) -> bool:
        if self._process is not None:
            return False
        program, base_args = resolve_cli_invocation(settings.cli_command)
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments(base_args + extra_args)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        self._command_name = name
        self._last_output = ""
        self._process_error = ""
        self.command_started.emit(name)
        process.start()
        return True

    def _collect_output(self) -> str:
        if self._process is None:
            return self._process_error
        stdout = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        stderr = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        combined = "\n".join(part for part in [self._last_output, stdout, stderr, self._process_error] if part.strip())
        self._last_output = combined
        return combined

    def _on_error(self, _error: QProcess.ProcessError) -> None:
        if self._process is None:
            return
        self._process_error = self._process.errorString()

    def _on_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        if self._process is None or self._command_name is None:
            return
        output = self._collect_output()
        name = self._command_name
        ok = exit_code == 0
        if name == "status":
            status = parse_gateway_status_output(output)
            if not ok and not status.raw_output:
                status.summary = "Unable to inspect gateway status."
                status.detail_message = output.strip() or "The OpenClaw CLI command could not be executed."
                status.disabled_reason = "Gateway restart is unavailable until the CLI command works."
            self.service_status_changed.emit(status)
            self.command_finished.emit(name, ok, status.summary if ok else status.detail_message)
        else:
            message = output.strip() or ("Gateway restarted." if ok else "Gateway restart failed.")
            self.command_finished.emit(name, ok, message)
        self._process.deleteLater()
        self._process = None
        self._command_name = None
