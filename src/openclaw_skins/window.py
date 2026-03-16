from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from openclaw_skins.config import APP_NAME
from openclaw_skins.models import GatewayConnectionState, GatewayServiceStatus, SkinManifest
from openclaw_skins.theme import ThemeTokens, build_stylesheet


class StatusLight(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self._live = False

    @property
    def live(self) -> bool:
        return self._live

    def set_live(self, live: bool) -> None:
        if self._live == live:
            return
        self._live = live
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#51B36E" if self._live else "#D26452")
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class SkinHostWindow(QWidget):
    refresh_requested = Signal()
    restart_requested = Signal()
    always_on_top_toggled = Signal(bool)

    def __init__(self, manifest: SkinManifest, icon_path: Path, always_on_top: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self.design_size = QSize(*manifest.window_size)
        self._drag_offset: QPoint | None = None
        self._quitting = False
        self._tray_icon: QSystemTrayIcon | None = None
        self._restart_running = False
        self._can_restart = False
        self._restart_tooltip = "Gateway service is not installed."
        self._always_on_top = always_on_top

        self.setObjectName("RootWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(self._resolve_window_size())
        self.setStyleSheet(build_stylesheet(ThemeTokens()))

        self.frames = [QPixmap(str(path)) for path in manifest.frame_paths]
        self.current_frame_index = manifest.idle_frame

        self.background_label = QLabel(self)
        self.background_label.setGeometry(0, 0, self.width(), self.height())
        self.background_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.background_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_frame(self.current_frame_index)

        self.overlay_panel = QFrame(self)
        self.overlay_panel.setObjectName("OverlayPanel")
        self.overlay_panel.setGeometry(self._overlay_rect())

        panel_layout = QVBoxLayout(self.overlay_panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(10)

        self.panel_title = QLabel(manifest.display_name)
        self.panel_title.setObjectName("PanelTitle")
        panel_layout.addWidget(self.panel_title)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(10)
        self.status_light = StatusLight(self.overlay_panel)
        self.status_label = QLabel("Gateway offline")
        self.status_label.setObjectName("StatusLabel")
        status_row.addWidget(self.status_light, 0, Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self.status_label, 1)
        panel_layout.addLayout(status_row)

        self.detail_label = QLabel("Waiting for gateway activity.")
        self.detail_label.setObjectName("DetailLabel")
        self.detail_label.setWordWrap(True)
        panel_layout.addWidget(self.detail_label)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        self.refresh_button = QPushButton("Refresh")
        self.restart_button = QPushButton("Restart Gateway")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.restart_button.clicked.connect(self.restart_requested.emit)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.restart_button)
        panel_layout.addLayout(button_row)

        self.feedback_label = QLabel("")
        self.feedback_label.setObjectName("FeedbackLabel")
        self.feedback_label.setWordWrap(True)
        panel_layout.addWidget(self.feedback_label)

        self.always_on_top_checkbox = QCheckBox("Always on top")
        self.always_on_top_checkbox.toggled.connect(self._handle_always_on_top_toggled)
        panel_layout.addWidget(self.always_on_top_checkbox)

        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(manifest.animation_interval_ms)
        self.animation_timer.timeout.connect(self._advance_frame)

        if icon_path.exists() and QSystemTrayIcon.isSystemTrayAvailable():
            self._create_tray(icon_path)

        self.set_always_on_top(always_on_top, emit_signal=False)
        self.apply_service_status(GatewayServiceStatus())
        self.apply_connection_state(GatewayConnectionState())

    def prepare_to_quit(self) -> None:
        self._quitting = True

    def apply_connection_state(self, state: GatewayConnectionState) -> None:
        self.status_light.set_live(state.live)
        self.status_label.setText(state.status_text)
        self.detail_label.setText(state.detail_text)
        self.detail_label.setToolTip(state.last_error or state.detail_text)
        if self._tray_icon is not None:
            self._tray_icon.setToolTip(f"{APP_NAME}\n{state.status_text}")

    def apply_service_status(self, status: GatewayServiceStatus) -> None:
        self._can_restart = status.can_restart
        self._restart_tooltip = status.disabled_reason or status.detail_message
        self.restart_button.setEnabled(status.can_restart and not self._restart_running)
        self.restart_button.setToolTip(self._restart_tooltip)
        self._sync_restart_action()

    def set_action_running(self, action_name: str, running: bool) -> None:
        if action_name == "status":
            self.refresh_button.setEnabled(not running)
        elif action_name == "restart":
            self._restart_running = running
            self.restart_button.setEnabled(self._can_restart and not running)
            self._sync_restart_action()

    def set_busy(self, busy: bool) -> None:
        if busy:
            if not self.animation_timer.isActive():
                self.animation_timer.start()
        else:
            self.animation_timer.stop()
            self.current_frame_index = self.manifest.idle_frame
            self._apply_frame(self.current_frame_index)

    def show_feedback(self, message: str, success: bool) -> None:
        self.feedback_label.setText(message)
        color = "#51B36E" if success else "#F3C563"
        self.feedback_label.setStyleSheet(f"color: {color};")

    def set_always_on_top(self, enabled: bool, *, emit_signal: bool = True) -> None:
        self._always_on_top = enabled
        geometry = self.geometry()
        was_visible = self.isVisible()
        self.setUpdatesEnabled(False)
        try:
            self.hide()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
            self.show()
            self.setGeometry(geometry)
            if not was_visible:
                self.hide()
        finally:
            self.setUpdatesEnabled(True)
        self._sync_always_on_top_ui(enabled)
        if emit_signal:
            self.always_on_top_toggled.emit(enabled)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_in_drag_region(event.position().toPoint()):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting or self._tray_icon is None:
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()
        self._sync_toggle_action()

    def _overlay_rect(self) -> QRect:
        anchor_x = self._scale_x(self.manifest.overlay_anchor.x)
        anchor_y = self._scale_y(self.manifest.overlay_anchor.y)
        canvas = self._scale_rect(self.manifest.canvas_bounds)
        max_width = max(320, min(430, canvas.width() - max(anchor_x - canvas.x(), 0) - 20))
        max_height = max(138, min(190, canvas.height() - max(anchor_y - canvas.y(), 0) - 20))
        right_limit = max(12, self.width() - max_width - 12)
        bottom_limit = max(12, self.height() - max_height - 12)
        return QRect(min(anchor_x, right_limit), min(anchor_y, bottom_limit), max_width, max_height)

    def _apply_frame(self, index: int) -> None:
        pixmap = self.frames[index]
        self.background_label.setPixmap(
            pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _advance_frame(self) -> None:
        self.current_frame_index = 1 if self.current_frame_index == 0 else 0
        self._apply_frame(self.current_frame_index)

    def _is_in_drag_region(self, point: QPoint) -> bool:
        for region in self.manifest.drag_regions:
            if self._scale_rect(region).contains(point):
                return True
        return False

    def _create_tray(self, icon_path: Path) -> None:
        menu = QMenu()
        self.show_hide_action = QAction("Hide", menu)
        self.refresh_action = QAction("Refresh", menu)
        self.restart_action = QAction("Restart Gateway", menu)
        self.always_on_top_action = QAction("Always on Top", menu)
        self.always_on_top_action.setCheckable(True)
        quit_action = QAction("Quit", menu)

        self.show_hide_action.triggered.connect(self._toggle_visibility)
        self.refresh_action.triggered.connect(self.refresh_requested.emit)
        self.restart_action.triggered.connect(self.restart_requested.emit)
        self.always_on_top_action.toggled.connect(self._handle_always_on_top_toggled)
        quit_action.triggered.connect(self._quit_from_tray)

        menu.addAction(self.show_hide_action)
        menu.addAction(self.refresh_action)
        menu.addAction(self.restart_action)
        menu.addAction(self.always_on_top_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        tray = QSystemTrayIcon(QIcon(str(icon_path)), self)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray_icon = tray
        self._sync_toggle_action()
        self._sync_restart_action()

    def _toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
        self._sync_toggle_action()

    def _quit_from_tray(self) -> None:
        self.prepare_to_quit()
        QApplication.instance().quit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self._toggle_visibility()

    def _sync_toggle_action(self) -> None:
        if hasattr(self, "show_hide_action"):
            self.show_hide_action.setText("Hide" if self.isVisible() else "Show")

    def _sync_restart_action(self) -> None:
        if hasattr(self, "restart_action"):
            self.restart_action.setEnabled(self._can_restart and not self._restart_running)
            self.restart_action.setToolTip(self._restart_tooltip)

    def _sync_always_on_top_ui(self, enabled: bool) -> None:
        self.always_on_top_checkbox.blockSignals(True)
        self.always_on_top_checkbox.setChecked(enabled)
        self.always_on_top_checkbox.blockSignals(False)
        if hasattr(self, "always_on_top_action"):
            self.always_on_top_action.blockSignals(True)
            self.always_on_top_action.setChecked(enabled)
            self.always_on_top_action.blockSignals(False)

    def _handle_always_on_top_toggled(self, enabled: bool) -> None:
        if enabled == self._always_on_top:
            self._sync_always_on_top_ui(enabled)
            return
        self.set_always_on_top(enabled, emit_signal=True)

    def _resolve_window_size(self) -> QSize:
        screen = QApplication.primaryScreen()
        if screen is None:
            return self.design_size
        available = screen.availableGeometry()
        width_ratio = (available.width() * 0.88) / self.design_size.width()
        height_ratio = (available.height() * 0.88) / self.design_size.height()
        scale = min(width_ratio, height_ratio, 1.0)
        return QSize(
            max(420, int(self.design_size.width() * scale)),
            max(260, int(self.design_size.height() * scale)),
        )

    def _scale_x(self, value: int) -> int:
        return round(value * self.width() / self.design_size.width())

    def _scale_y(self, value: int) -> int:
        return round(value * self.height() / self.design_size.height())

    def _scale_rect(self, rect) -> QRect:
        return QRect(
            self._scale_x(rect.x),
            self._scale_y(rect.y),
            self._scale_x(rect.width),
            self._scale_y(rect.height),
        )
