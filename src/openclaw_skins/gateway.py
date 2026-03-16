from __future__ import annotations

import json
import locale
import platform
import time
import uuid

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket

from openclaw_skins.config import (
    APP_NAME,
    APP_SLUG,
    APP_VERSION,
    DEFAULT_TICK_INTERVAL_MS,
    PROTOCOL_VERSION,
    RECONNECT_DELAY_MS,
)
from openclaw_skins.device_auth import clear_device_auth_token, load_device_auth_token, store_device_auth_token
from openclaw_skins.identity import (
    DeviceIdentity,
    load_or_create_device_identity,
    public_key_raw_base64url_from_pem,
    sign_device_payload,
)
from openclaw_skins.models import GatewayConnectionState


def monotonic_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def normalize_device_metadata_for_auth(value: str | None) -> str:
    if not value:
        return ""
    normalized_chars: list[str] = []
    for char in value.strip():
        code = ord(char)
        normalized_chars.append(chr(code + 32) if 65 <= code <= 90 else char)
    return "".join(normalized_chars)


def build_device_auth_payload_v3(
    *,
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    signed_at_ms: int,
    token: str,
    nonce: str,
    platform_label: str,
    device_family: str,
) -> str:
    return "|".join(
        [
            "v3",
            device_id,
            client_id,
            client_mode,
            role,
            ",".join(scopes),
            str(signed_at_ms),
            token,
            nonce,
            normalize_device_metadata_for_auth(platform_label),
            normalize_device_metadata_for_auth(device_family),
        ]
    )


def build_connect_params(
    *,
    gateway_token: str = "",
    bootstrap_token: str = "",
    device_token: str = "",
    device_identity: DeviceIdentity | None = None,
    nonce: str = "",
) -> dict[str, object]:
    locale_code = locale.getlocale()[0] or "en_US"
    normalized_locale = locale_code.replace("_", "-")
    platform_label = platform.system() or platform.platform()
    device_family = "desktop"
    instance_suffix = platform.node().strip().lower().replace(" ", "-") or "desktop"
    client_id = "gateway-client"
    client_mode = "backend"
    role = "operator"
    scopes = ["operator.read"]

    params: dict[str, object] = {
        "minProtocol": PROTOCOL_VERSION,
        "maxProtocol": PROTOCOL_VERSION,
        "client": {
            "id": client_id,
            "displayName": APP_NAME,
            "version": APP_VERSION,
            "platform": platform_label,
            "deviceFamily": device_family,
            "mode": client_mode,
            "instanceId": f"{APP_SLUG}-{instance_suffix}",
        },
        "caps": [],
        "role": role,
        "scopes": scopes,
        "locale": normalized_locale,
        "userAgent": f"{APP_NAME}/{APP_VERSION} ({platform_label})",
    }

    trimmed_gateway_token = gateway_token.strip()
    trimmed_bootstrap_token = bootstrap_token.strip()
    trimmed_device_token = device_token.strip()
    signature_token = ""
    auth_payload: dict[str, str] = {}
    if trimmed_gateway_token:
        auth_payload["token"] = trimmed_gateway_token
        signature_token = trimmed_gateway_token
    elif trimmed_device_token:
        auth_payload["token"] = trimmed_device_token
        signature_token = trimmed_device_token
    elif trimmed_bootstrap_token:
        auth_payload["bootstrapToken"] = trimmed_bootstrap_token
        signature_token = trimmed_bootstrap_token
    if auth_payload:
        params["auth"] = auth_payload

    trimmed_nonce = nonce.strip()
    if device_identity is not None and trimmed_nonce:
        signed_at_ms = int(time.time() * 1000)
        payload = build_device_auth_payload_v3(
            device_id=device_identity.device_id,
            client_id=client_id,
            client_mode=client_mode,
            role=role,
            scopes=scopes,
            signed_at_ms=signed_at_ms,
            token=signature_token,
            nonce=trimmed_nonce,
            platform_label=platform_label,
            device_family=device_family,
        )
        params["device"] = {
            "id": device_identity.device_id,
            "publicKey": public_key_raw_base64url_from_pem(device_identity.public_key_pem),
            "signature": sign_device_payload(device_identity.private_key_pem, payload),
            "signedAt": signed_at_ms,
            "nonce": trimmed_nonce,
        }
    return params


class OpenClawGatewayClient(QObject):
    connection_state_changed = Signal(object)
    snapshot_received = Signal(object)
    agent_event_received = Signal(str, str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._socket: QWebSocket | None = None
        self._desired_url = ""
        self._desired_token = ""
        self._desired_bootstrap_token = ""
        self._manual_stop = False
        self._connect_request_id: str | None = None
        self._handshake_complete = False
        self._last_seen_ms: int | None = None
        self._last_error = ""
        self._tick_interval_ms = DEFAULT_TICK_INTERVAL_MS
        self._state = GatewayConnectionState()
        self._device_identity = load_or_create_device_identity()

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._connect_socket)

        self._liveness_timer = QTimer(self)
        self._liveness_timer.setInterval(1_000)
        self._liveness_timer.timeout.connect(self._refresh_liveness)
        self._liveness_timer.start()

    def start(self, url: str, token: str = "", bootstrap_token: str = "") -> None:
        self._desired_url = url.strip()
        self._desired_token = token.strip()
        self._desired_bootstrap_token = bootstrap_token.strip()
        self._manual_stop = False
        self._reconnect_timer.stop()
        self._connect_socket()

    def reconnect_now(self) -> None:
        self._manual_stop = False
        self._reconnect_timer.stop()
        self._connect_socket()

    def stop(self) -> None:
        self._manual_stop = True
        self._reconnect_timer.stop()
        self._handshake_complete = False
        self._last_seen_ms = None
        self._teardown_socket()
        self._emit_state(
            transport_connected=False,
            handshake_complete=False,
            live=False,
            status_text="Gateway offline",
            detail_text="Disconnected.",
            last_error=self._last_error or None,
        )

    def _connect_socket(self) -> None:
        self._teardown_socket()
        if not self._desired_url:
            self._emit_state(
                transport_connected=False,
                handshake_complete=False,
                live=False,
                status_text="Gateway offline",
                detail_text="No gateway URL configured.",
                last_error="No gateway URL configured.",
            )
            return

        self._handshake_complete = False
        self._last_seen_ms = None
        self._connect_request_id = None
        self._socket = QWebSocket()
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.textMessageReceived.connect(self._on_text_message)
        self._socket.errorOccurred.connect(self._on_error)
        self._emit_state(
            transport_connected=False,
            handshake_complete=False,
            live=False,
            status_text="Connecting...",
            detail_text=f"Opening {self._desired_url}",
            last_error=None,
        )
        self._socket.open(QUrl(self._desired_url))

    def _teardown_socket(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.abort()
        finally:
            self._socket.deleteLater()
            self._socket = None

    def _on_connected(self) -> None:
        self._emit_state(
            transport_connected=True,
            handshake_complete=False,
            live=False,
            status_text="Connected...",
            detail_text="Waiting for gateway handshake.",
            last_error=None,
        )

    def _on_disconnected(self) -> None:
        detail = self._last_error or "Gateway connection closed."
        self._handshake_complete = False
        self._last_seen_ms = None
        self._emit_state(
            transport_connected=False,
            handshake_complete=False,
            live=False,
            status_text="Gateway offline",
            detail_text=detail,
            last_error=self._last_error or None,
        )
        if not self._manual_stop:
            self._reconnect_timer.start(RECONNECT_DELAY_MS)

    def _on_error(self, _error: QAbstractSocket.SocketError) -> None:
        if self._socket is None:
            return
        self._last_error = self._socket.errorString().strip()
        self._emit_state(
            transport_connected=False,
            handshake_complete=self._handshake_complete,
            live=False,
            status_text="Gateway offline",
            detail_text=self._last_error or "Connection failed.",
            last_error=self._last_error or None,
        )

    def _on_text_message(self, raw_message: str) -> None:
        try:
            frame = json.loads(raw_message)
        except json.JSONDecodeError:
            return
        if not isinstance(frame, dict):
            return

        frame_type = frame.get("type")
        if frame_type == "event":
            event = str(frame.get("event", "")).strip()
            payload = frame.get("payload")
            if event == "connect.challenge":
                nonce = ""
                if isinstance(payload, dict):
                    nonce = str(payload.get("nonce", "")).strip()
                self._send_connect(nonce)
                return

            self._touch_alive()
            if event == "agent" and isinstance(payload, dict):
                run_id = str(payload.get("runId", "")).strip()
                stream = str(payload.get("stream", "")).strip()
                data = payload.get("data", {})
                if run_id and stream:
                    self.agent_event_received.emit(run_id, stream, data)
            self._refresh_liveness()
            return

        if frame_type == "res" and frame.get("id") == self._connect_request_id:
            if frame.get("ok"):
                payload = frame.get("payload", {})
                self._handle_hello(payload if isinstance(payload, dict) else {})
            else:
                error = frame.get("error", {})
                message = (
                    str(error.get("message", "Gateway handshake failed.")).strip()
                    if isinstance(error, dict)
                    else "Gateway handshake failed."
                )
                self._last_error = message
                if "device token mismatch" in message.lower():
                    clear_device_auth_token(self._device_identity.device_id, "operator")
                self._emit_state(
                    transport_connected=False,
                    handshake_complete=False,
                    live=False,
                    status_text="Gateway offline",
                    detail_text=message,
                    last_error=message,
                )
                if self._socket is not None:
                    self._socket.abort()

    def _send_connect(self, nonce: str) -> None:
        if self._socket is None:
            return
        self._connect_request_id = str(uuid.uuid4())
        stored_device_token = ""
        stored_entry = load_device_auth_token(self._device_identity.device_id, "operator")
        if stored_entry is not None:
            stored_device_token = stored_entry.token
        frame = {
            "type": "req",
            "id": self._connect_request_id,
            "method": "connect",
            "params": build_connect_params(
                gateway_token=self._desired_token,
                bootstrap_token=self._desired_bootstrap_token,
                device_token=stored_device_token,
                device_identity=self._device_identity,
                nonce=nonce,
            ),
        }
        self._socket.sendTextMessage(json.dumps(frame))

    def _handle_hello(self, payload: dict[str, object]) -> None:
        self._handshake_complete = True
        policy = payload.get("policy", {})
        if isinstance(policy, dict):
            tick_interval = policy.get("tickIntervalMs")
            if isinstance(tick_interval, int) and tick_interval > 0:
                self._tick_interval_ms = tick_interval
        auth_info = payload.get("auth", {})
        if isinstance(auth_info, dict):
            device_token = auth_info.get("deviceToken")
            role = auth_info.get("role")
            scopes = auth_info.get("scopes")
            if isinstance(device_token, str) and device_token.strip():
                store_device_auth_token(
                    self._device_identity.device_id,
                    role.strip() if isinstance(role, str) else "operator",
                    device_token.strip(),
                    scopes if isinstance(scopes, list) else None,
                )
        snapshot = payload.get("snapshot", {})
        self.snapshot_received.emit(snapshot if isinstance(snapshot, dict) else {})
        self._touch_alive()
        self._emit_state(
            transport_connected=True,
            handshake_complete=True,
            live=True,
            status_text="Gateway live",
            detail_text=f"Connected to {self._desired_url}",
            last_error=None,
            tick_interval_ms=self._tick_interval_ms,
        )

    def _touch_alive(self) -> None:
        self._last_seen_ms = monotonic_ms()
        self._last_error = ""

    def _refresh_liveness(self) -> None:
        if not self._handshake_complete:
            return
        if self._last_seen_ms is None:
            self._emit_state(
                transport_connected=True,
                handshake_complete=True,
                live=False,
                status_text="Gateway stale",
                detail_text="Waiting for gateway activity.",
                last_error=None,
                tick_interval_ms=self._tick_interval_ms,
            )
            return
        stale_after_ms = max(self._tick_interval_ms * 2, 5_000)
        live = monotonic_ms() - self._last_seen_ms <= stale_after_ms
        self._emit_state(
            transport_connected=True,
            handshake_complete=True,
            live=live,
            status_text="Gateway live" if live else "Gateway stale",
            detail_text="Gateway heartbeat is healthy." if live else "No recent gateway tick or event was received.",
            last_error=None if live else self._state.last_error,
            tick_interval_ms=self._tick_interval_ms,
        )

    def _emit_state(
        self,
        *,
        transport_connected: bool,
        handshake_complete: bool,
        live: bool,
        status_text: str,
        detail_text: str,
        last_error: str | None,
        tick_interval_ms: int | None = None,
    ) -> None:
        self._state = GatewayConnectionState(
            transport_connected=transport_connected,
            handshake_complete=handshake_complete,
            live=live,
            status_text=status_text,
            detail_text=detail_text,
            last_error=last_error,
            tick_interval_ms=tick_interval_ms or self._tick_interval_ms,
        )
        self.connection_state_changed.emit(self._state)
