from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from openclaw_skins.cli import OpenClawCliBridge
from openclaw_skins.gateway import OpenClawGatewayClient
from openclaw_skins.models import BusyRunTracker, GatewayServiceStatus, Point
from openclaw_skins.settings import AppSettingsStore


class OpenClawController(QObject):
    connection_state_changed = Signal(object)
    service_status_changed = Signal(object)
    busy_changed = Signal(bool)
    feedback_changed = Signal(str, bool)
    action_running_changed = Signal(str, bool)

    def __init__(
        self,
        settings_store: AppSettingsStore,
        gateway_client: OpenClawGatewayClient | None = None,
        cli_bridge: OpenClawCliBridge | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_store = settings_store
        self.gateway_client = gateway_client or OpenClawGatewayClient(self)
        self.cli_bridge = cli_bridge or OpenClawCliBridge(self)
        self.busy_tracker = BusyRunTracker()
        self._service_status = GatewayServiceStatus()

        self.gateway_client.connection_state_changed.connect(self._on_connection_state)
        self.gateway_client.agent_event_received.connect(self._on_agent_event)
        self.cli_bridge.service_status_changed.connect(self._on_service_status)
        self.cli_bridge.command_finished.connect(self._on_command_finished)

    def start(self) -> None:
        self.refresh()

    def shutdown(self) -> None:
        self.gateway_client.stop()
        self.cli_bridge.cancel()

    def refresh(self) -> None:
        settings = self.settings_store.settings
        self.busy_tracker.clear()
        self.busy_changed.emit(False)
        if self.cli_bridge.check_gateway_status(settings):
            self.action_running_changed.emit("status", True)
        self.gateway_client.start(settings.gateway_url, settings.gateway_token)

    def restart_gateway(self) -> None:
        if not self._service_status.can_restart:
            self.feedback_changed.emit(self._service_status.disabled_reason, False)
            return
        if self.cli_bridge.restart_gateway(self.settings_store.settings):
            self.action_running_changed.emit("restart", True)

    def set_always_on_top(self, enabled: bool) -> None:
        self.settings_store.update(always_on_top=enabled)

    def save_window_position(self, x: int, y: int) -> None:
        self.settings_store.update(window_position=Point(x=x, y=y))

    def _on_connection_state(self, state: object) -> None:
        self.connection_state_changed.emit(state)
        if getattr(state, "transport_connected", False):
            return
        if self.busy_tracker.busy:
            self.busy_tracker.clear()
            self.busy_changed.emit(False)

    def _on_agent_event(self, run_id: str, stream: str, data: object) -> None:
        before = self.busy_tracker.busy
        after = self.busy_tracker.apply_agent_event(run_id, stream, data)
        if after != before:
            self.busy_changed.emit(after)

    def _on_service_status(self, status: object) -> None:
        if isinstance(status, GatewayServiceStatus):
            self._service_status = status
        self.action_running_changed.emit("status", False)
        self.service_status_changed.emit(status)

    def _on_command_finished(self, name: str, ok: bool, message: str) -> None:
        self.action_running_changed.emit(name, False)
        if name == "restart":
            self.feedback_changed.emit(message, ok)
            if ok:
                QTimer.singleShot(1_000, self.refresh)
        elif not ok:
            self.feedback_changed.emit(message, False)
