from __future__ import annotations

import os
import re
import shlex
import subprocess

from PySide6.QtCore import QObject, QProcess, Signal

from openclaw_skins.models import AppSettings, GatewayServiceStatus


def split_cli_command(command: str) -> tuple[str, list[str]]:
    parts = shlex.split(command, posix=False)
    cleaned = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part for part in parts]
    if not cleaned:
        raise ValueError("cli command cannot be empty")
    return cleaned[0], cleaned[1:]


def discover_gateway_token(settings: AppSettings, timeout_seconds: float = 4.0) -> str:
    explicit_token = settings.gateway_token.strip()
    if explicit_token:
        return explicit_token

    for env_name in ("OPENCLAW_GATEWAY_TOKEN", "CLAWDBOT_GATEWAY_TOKEN"):
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            return env_value

    try:
        program, base_args = split_cli_command(settings.cli_command)
    except ValueError:
        return ""

    try:
        completed = subprocess.run(
            [program, *base_args, "config", "get", "gateway.auth.token"],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if completed.returncode != 0:
        return ""

    candidate = completed.stdout.strip()
    if not candidate:
        return ""
    if candidate.startswith("${") and candidate.endswith("}"):
        return ""
    if candidate.lower() in {"null", "none", "undefined"}:
        return ""
    return candidate


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

    def cancel(self) -> None:
        if self._process is not None:
            self._process.kill()
            self._process = None
            self._command_name = None

    def _start(self, name: str, settings: AppSettings, extra_args: list[str]) -> bool:
        if self._process is not None:
            return False
        program, base_args = split_cli_command(settings.cli_command)
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
