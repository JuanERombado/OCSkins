from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from openclaw_skins.models import GatewayConnectionState, GatewayServiceStatus, Point, Rect, SkinManifest
from openclaw_skins.window import SkinHostWindow


def _write_frame(path: Path, color: int) -> None:
    image = QImage(120, 80, QImage.Format.Format_ARGB32)
    image.fill(color)
    image.save(str(path))


def build_manifest(tmp_path) -> SkinManifest:
    frame_a = tmp_path / "frame-a.png"
    frame_b = tmp_path / "frame-b.png"
    _write_frame(frame_a, 0x11AA8844)
    _write_frame(frame_b, 0x22CC6644)
    return SkinManifest(
        skin_id="test",
        display_name="Test Skin",
        frame_paths=(frame_a, frame_b),
        window_size=(320, 220),
        canvas_bounds=Rect(x=50, y=40, width=220, height=120),
        drag_regions=(Rect(x=0, y=0, width=320, height=140),),
        idle_frame=0,
        animation_interval_ms=80,
        overlay_anchor=Point(x=80, y=60),
        manifest_path=tmp_path / "skin.json",
    )


def test_window_updates_indicator_and_restart_state(qtbot, tmp_path) -> None:
    window = SkinHostWindow(build_manifest(tmp_path), tmp_path / "missing-icon.png")
    qtbot.addWidget(window)

    window.apply_connection_state(
        GatewayConnectionState(
            transport_connected=False,
            handshake_complete=False,
            live=False,
            status_text="Gateway offline",
            detail_text="No connection.",
        )
    )
    window.apply_service_status(
        GatewayServiceStatus(
            service_present=False,
            can_restart=False,
            summary="Gateway service is not installed.",
            detail_message="Install the gateway service first.",
            disabled_reason="Gateway service is not installed.",
            runtime_label="",
            raw_output="",
        )
    )

    assert window.status_light.live is False
    assert window.restart_button.isEnabled() is False

    window.apply_connection_state(
        GatewayConnectionState(
            transport_connected=True,
            handshake_complete=True,
            live=True,
            status_text="Gateway live",
            detail_text="Connected to ws://127.0.0.1:18789",
        )
    )
    window.apply_service_status(
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

    assert window.status_light.live is True
    assert window.status_label.text() == "Gateway live"
    assert window.restart_button.isEnabled() is True


def test_window_animates_between_frames_while_busy(qtbot, tmp_path) -> None:
    manifest = build_manifest(tmp_path)
    window = SkinHostWindow(manifest, tmp_path / "missing-icon.png")
    qtbot.addWidget(window)

    assert window.current_frame_index == manifest.idle_frame
    window.set_busy(True)
    qtbot.wait(manifest.animation_interval_ms + 40)
    assert window.current_frame_index != manifest.idle_frame

    window.set_busy(False)
    assert window.animation_timer.isActive() is False
    assert window.current_frame_index == manifest.idle_frame


def test_window_emits_button_requests(qtbot, tmp_path) -> None:
    window = SkinHostWindow(build_manifest(tmp_path), tmp_path / "missing-icon.png")
    qtbot.addWidget(window)
    events: list[str] = []
    window.refresh_requested.connect(lambda: events.append("refresh"))
    window.restart_requested.connect(lambda: events.append("restart"))
    window.apply_service_status(
        GatewayServiceStatus(
            service_present=True,
            can_restart=True,
            summary="Gateway service is running.",
            detail_message="running",
            disabled_reason="",
            runtime_label="running",
            raw_output="",
        )
    )

    qtbot.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.restart_button, Qt.MouseButton.LeftButton)

    assert events == ["refresh", "restart"]


def test_window_emits_always_on_top_toggle(qtbot, tmp_path) -> None:
    window = SkinHostWindow(build_manifest(tmp_path), tmp_path / "missing-icon.png")
    qtbot.addWidget(window)
    toggles: list[bool] = []
    window.always_on_top_toggled.connect(toggles.append)

    qtbot.mouseClick(window.always_on_top_checkbox, Qt.MouseButton.LeftButton)

    assert toggles == [True]
    assert window.always_on_top_checkbox.isChecked() is True


def test_overlay_panel_uses_most_of_canvas_space(qtbot, tmp_path) -> None:
    manifest = build_manifest(tmp_path)
    window = SkinHostWindow(manifest, tmp_path / "missing-icon.png")
    qtbot.addWidget(window)

    canvas = window._scale_rect(manifest.canvas_bounds)

    assert window.overlay_panel.width() >= int(canvas.width() * 0.85)
    assert window.overlay_panel.height() >= int(canvas.height() * 0.8)


def test_window_scale_controls_resize_the_skin(qtbot, tmp_path) -> None:
    window = SkinHostWindow(build_manifest(tmp_path), tmp_path / "missing-icon.png")
    qtbot.addWidget(window)
    scales: list[float] = []
    window.window_scale_changed.connect(scales.append)
    original_size = window.size()

    qtbot.mouseClick(window.smaller_button, Qt.MouseButton.LeftButton)

    assert window.width() < original_size.width()
    assert scales

    qtbot.mouseClick(window.larger_button, Qt.MouseButton.LeftButton)
    assert window.width() >= original_size.width() - 5


def test_window_resize_updates_overlay_geometry(qtbot, tmp_path) -> None:
    manifest = build_manifest(tmp_path)
    window = SkinHostWindow(manifest, tmp_path / "missing-icon.png", initial_scale=0.6)
    qtbot.addWidget(window)
    original_overlay_width = window.overlay_panel.width()

    window.set_window_scale(0.8, emit_signal=False)

    assert window.overlay_panel.width() > original_overlay_width
    assert window.background_label.width() == window.width()
