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
        self._transient_busy = False
        self._last_busy_state = False
        self._activity_hold_timer = QTimer(self)
        self._activity_hold_timer.setSingleShot(True)
        self._activity_hold_timer.setInterval(1_400)
        self._activity_hold_timer.timeout.connect(self._clear_transient_busy)

        self.gateway_client.connection_state_changed.connect(self._on_connection_state)
        self.gateway_client.agent_event_received.connect(self._on_agent_event)
        self.gateway_client.activity_detected.connect(self._on_gateway_activity)
        self.cli_bridge.service_status_changed.connect(self._on_service_status)
        self.cli_bridge.command_finished.connect(self._on_command_finished)

    def start(self) -> None:
        self.refresh()

    def shutdown(self) -> None:
        self.gateway_client.stop()
        self.cli_bridge.cancel()

    def refresh(self) -> None:
        settings = self.settings_store.settings
        auth = self.cli_bridge.discover_gateway_auth(settings)
        self.busy_tracker.clear()
        self._transient_busy = False
        self._activity_hold_timer.stop()
        self._emit_busy_state()
        if self.cli_bridge.check_gateway_status(settings):
            self.action_running_changed.emit("status", True)
        self.gateway_client.start(
            auth.gateway_url or settings.gateway_url,
            auth.gateway_token,
            auth.bootstrap_token,
        )

    def restart_gateway(self) -> None:
        if not self._service_status.can_restart:
            self.feedback_changed.emit(self._service_status.disabled_reason, False)
            return
        if self.cli_bridge.restart_gateway(self.settings_store.settings):
            self.action_running_changed.emit("restart", True)

    def set_always_on_top(self, enabled: bool) -> None:
        self.settings_store.update(always_on_top=enabled)

    def set_window_scale(self, scale: float) -> None:
        self.settings_store.update(window_scale=scale)

    def save_window_position(self, x: int, y: int) -> None:
        self.settings_store.update(window_position=Point(x=x, y=y))

    def _on_connection_state(self, state: object) -> None:
        self.connection_state_changed.emit(state)
        if getattr(state, "transport_connected", False):
            return
        if self.busy_tracker.busy or self._transient_busy:
            self.busy_tracker.clear()
            self._transient_busy = False
            self._activity_hold_timer.stop()
            self._emit_busy_state()

    def _on_agent_event(self, run_id: str, stream: str, data: object) -> None:
        self.busy_tracker.apply_agent_event(run_id, stream, data)
        self._emit_busy_state()

    def _on_gateway_activity(self, _event_name: str) -> None:
        self._transient_busy = True
        self._activity_hold_timer.start()
        self._emit_busy_state()

    def _clear_transient_busy(self) -> None:
        self._transient_busy = False
        self._emit_busy_state()

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

    def _emit_busy_state(self) -> None:
        busy = self.busy_tracker.busy or self._transient_busy
        if busy == self._last_busy_state:
            return
        self._last_busy_state = busy
        self.busy_changed.emit(busy)
