from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from openclaw_skins.controller import OpenClawController
from openclaw_skins.models import GatewayServiceStatus
from openclaw_skins.settings import AppSettingsStore


class FakeGatewayClient(QObject):
    connection_state_changed = Signal(object)
    snapshot_received = Signal(object)
    agent_event_received = Signal(str, str, object)

    def __init__(self) -> None:
        super().__init__()
        self.started_with: tuple[str, str] | None = None
        self.stopped = False

    def start(self, url: str, token: str = "") -> None:
        self.started_with = (url, token)

    def stop(self) -> None:
        self.stopped = True


class FakeCliBridge(QObject):
    service_status_changed = Signal(object)
    command_finished = Signal(str, bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.status_requested = False
        self.restart_requested = False
        self.cancelled = False

    def check_gateway_status(self, _settings) -> bool:
        self.status_requested = True
        return True

    def restart_gateway(self, _settings) -> bool:
        self.restart_requested = True
        return True

    def cancel(self) -> None:
        self.cancelled = True


def test_controller_refresh_starts_gateway_and_status_probe(tmp_path) -> None:
    store = AppSettingsStore(tmp_path / "settings.json")
    fake_gateway = FakeGatewayClient()
    fake_cli = FakeCliBridge()
    controller = OpenClawController(store, gateway_client=fake_gateway, cli_bridge=fake_cli)

    controller.refresh()

    assert fake_cli.status_requested is True
    assert fake_gateway.started_with == (store.settings.gateway_url, store.settings.gateway_token)


def test_controller_restart_failure_emits_feedback(tmp_path) -> None:
    store = AppSettingsStore(tmp_path / "settings.json")
    fake_gateway = FakeGatewayClient()
    fake_cli = FakeCliBridge()
    controller = OpenClawController(store, gateway_client=fake_gateway, cli_bridge=fake_cli)
    feedback: list[tuple[str, bool]] = []
    controller.feedback_changed.connect(lambda message, success: feedback.append((message, success)))

    fake_cli.service_status_changed.emit(
        GatewayServiceStatus(
            service_present=True,
            can_restart=True,
            summary="Gateway service is running.",
            detail_message="running (PID 1234)",
            disabled_reason="",
            runtime_label="running (PID 1234)",
            raw_output="",
        )
    )
    controller.restart_gateway()
    fake_cli.command_finished.emit("restart", False, "permission denied")

    assert fake_cli.restart_requested is True
    assert feedback[-1] == ("permission denied", False)

