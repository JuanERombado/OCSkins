from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QIcon,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
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
        self.setFixedSize(24, 24)
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
    window_scale_changed = Signal(float)

    def __init__(
        self,
        manifest: SkinManifest,
        icon_path: Path,
        always_on_top: bool = False,
        initial_scale: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
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
        self._window_scale = 1.0
        self._resize_origin_global: QPoint | None = None
        self._resize_origin_size = QSize()
        self._resize_origin_scale = 1.0
        self._resize_handle_size = 34
        self._scale_step = 0.1
        self._wheel_scale_step = 0.05

        self.setObjectName("RootWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setWindowTitle(APP_NAME)
        self.setStyleSheet(build_stylesheet(ThemeTokens()))

        self.frames = [QPixmap(str(path)) for path in manifest.frame_paths]
        self.current_frame_index = manifest.idle_frame

        self.background_label = QLabel(self)
        self.background_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.background_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.overlay_panel = QFrame(self)
        self.overlay_panel.setObjectName("OverlayPanel")

        panel_layout = QVBoxLayout(self.overlay_panel)
        panel_layout.setContentsMargins(38, 30, 38, 24)
        panel_layout.setSpacing(18)

        self.panel_title = QLabel(manifest.display_name)
        self.panel_title.setObjectName("PanelTitle")
        self.panel_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        panel_layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(14)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("SecondaryButton")
        self.restart_button = QPushButton("Restart Gateway")
        self.restart_button.setObjectName("PrimaryButton")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.restart_button.clicked.connect(self.restart_requested.emit)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.restart_button)
        panel_layout.addLayout(button_row)

        self.feedback_label = QLabel("")
        self.feedback_label.setObjectName("FeedbackLabel")
        self.feedback_label.setWordWrap(True)
        panel_layout.addWidget(self.feedback_label)

        utility_row = QHBoxLayout()
        utility_row.setContentsMargins(0, 0, 0, 0)
        utility_row.setSpacing(12)

        self.always_on_top_checkbox = QCheckBox("Always on top")
        self.always_on_top_checkbox.toggled.connect(self._handle_always_on_top_toggled)
        utility_row.addWidget(self.always_on_top_checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
        utility_row.addStretch(1)

        self.scale_label = QLabel("")
        self.scale_label.setObjectName("ScaleLabel")
        self.scale_label.setToolTip("Use the size buttons, Ctrl+mouse wheel, or drag the lower-right corner.")
        utility_row.addWidget(self.scale_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.smaller_button = QPushButton("-")
        self.smaller_button.setObjectName("UtilityButton")
        self.reset_size_button = QPushButton("Reset")
        self.reset_size_button.setObjectName("UtilityButton")
        self.larger_button = QPushButton("+")
        self.larger_button.setObjectName("UtilityButton")
        self.smaller_button.clicked.connect(lambda: self.adjust_window_scale(-self._scale_step))
        self.reset_size_button.clicked.connect(self.reset_window_scale)
        self.larger_button.clicked.connect(lambda: self.adjust_window_scale(self._scale_step))
        utility_row.addWidget(self.smaller_button)
        utility_row.addWidget(self.reset_size_button)
        utility_row.addWidget(self.larger_button)
        panel_layout.addLayout(utility_row)

        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(manifest.animation_interval_ms)
        self.animation_timer.timeout.connect(self._advance_frame)

        if icon_path.exists() and QSystemTrayIcon.isSystemTrayAvailable():
            self._create_tray(icon_path)

        self.set_always_on_top(always_on_top, emit_signal=False)
        self.set_window_scale(initial_scale, emit_signal=False, anchor="top-left")
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

    def set_window_scale(
        self,
        scale: float,
        *,
        emit_signal: bool = True,
        anchor: str = "center",
    ) -> None:
        clamped = self._clamp_scale(scale)
        if abs(clamped - self._window_scale) < 0.001 and self.size() == self._size_for_scale(clamped):
            self._sync_scale_ui()
            return
        current_geometry = self.geometry()
        target_size = self._size_for_scale(clamped)
        self._window_scale = clamped
        self.resize(target_size)
        if anchor == "top-left":
            self.move(current_geometry.topLeft())
        else:
            center = current_geometry.center()
            self.move(center.x() - target_size.width() // 2, center.y() - target_size.height() // 2)
        self._update_window_layout()
        self._sync_scale_ui()
        if emit_signal:
            self.window_scale_changed.emit(round(clamped, 3))

    def adjust_window_scale(self, delta: float) -> None:
        self.set_window_scale(self._window_scale + delta)

    def reset_window_scale(self) -> None:
        self.set_window_scale(self._default_scale())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and self._resize_handle_rect().contains(point):
            self._resize_origin_global = event.globalPosition().toPoint()
            self._resize_origin_size = self.size()
            self._resize_origin_scale = self._window_scale
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._is_in_drag_region(point):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if self._resize_origin_global is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._resize_origin_global
            width_scale = (self._resize_origin_size.width() + delta.x()) / self.design_size.width()
            height_scale = (self._resize_origin_size.height() + delta.y()) / self.design_size.height()
            self.set_window_scale(min(width_scale, height_scale), anchor="top-left")
            event.accept()
            return
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        if self._resize_handle_rect().contains(point):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif self.cursor().shape() == Qt.CursorShape.SizeFDiagCursor:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        self._resize_origin_global = None
        self._resize_origin_size = QSize()
        if self._resize_handle_rect().contains(event.position().toPoint()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.unsetCursor()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = self._wheel_scale_step if event.angleDelta().y() > 0 else -self._wheel_scale_step
            self.adjust_window_scale(delta)
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_window_layout()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting or self._tray_icon is None:
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()
        self._sync_toggle_action()

    def _overlay_rect(self) -> QRect:
        canvas = self._scale_rect(self.manifest.canvas_bounds)
        inset_x = max(48, round(canvas.width() * 0.09))
        inset_y_top = max(48, round(canvas.height() * 0.1))
        inset_y_bottom = max(42, round(canvas.height() * 0.14))
        target_width = max(360, round(canvas.width() * 0.72))
        target_height = max(260, round(canvas.height() * 0.64))
        centered_x = canvas.x() + (canvas.width() - target_width) // 2
        centered_y = canvas.y() + max(0, round(canvas.height() * 0.06))
        rect = QRect(centered_x, centered_y, target_width, target_height)
        inner_bounds = canvas.adjusted(inset_x, inset_y_top, -inset_x, -inset_y_bottom)
        rect = rect.intersected(inner_bounds)
        min_width = max(320, round(canvas.width() * 0.54))
        min_height = max(220, round(canvas.height() * 0.48))
        if rect.width() < min_width:
            rect.setWidth(min_width)
            rect.moveLeft(canvas.x() + (canvas.width() - rect.width()) // 2)
        if rect.height() < min_height:
            rect.setHeight(min_height)
            rect.moveTop(canvas.y() + max(0, round(canvas.height() * 0.09)))
        return rect.intersected(QRect(12, 12, self.width() - 24, self.height() - 24))

    def _apply_frame(self, index: int) -> None:
        pixmap = self.frames[index]
        if pixmap.isNull():
            self.background_label.clear()
            return
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
        self.smaller_action = QAction("Smaller", menu)
        self.reset_size_action = QAction("Reset Size", menu)
        self.larger_action = QAction("Larger", menu)
        quit_action = QAction("Quit", menu)

        self.show_hide_action.triggered.connect(self._toggle_visibility)
        self.refresh_action.triggered.connect(self.refresh_requested.emit)
        self.restart_action.triggered.connect(self.restart_requested.emit)
        self.always_on_top_action.toggled.connect(self._handle_always_on_top_toggled)
        self.smaller_action.triggered.connect(lambda: self.adjust_window_scale(-self._scale_step))
        self.reset_size_action.triggered.connect(self.reset_window_scale)
        self.larger_action.triggered.connect(lambda: self.adjust_window_scale(self._scale_step))
        quit_action.triggered.connect(self._quit_from_tray)

        menu.addAction(self.show_hide_action)
        menu.addAction(self.refresh_action)
        menu.addAction(self.restart_action)
        menu.addAction(self.always_on_top_action)
        menu.addSeparator()
        menu.addAction(self.smaller_action)
        menu.addAction(self.reset_size_action)
        menu.addAction(self.larger_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        tray = QSystemTrayIcon(QIcon(str(icon_path)), self)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray_icon = tray
        self._sync_toggle_action()
        self._sync_restart_action()
        self._sync_scale_ui()

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

    def _sync_scale_ui(self) -> None:
        minimum_scale, maximum_scale = self._scale_bounds()
        percent = round(self._window_scale * 100)
        self.scale_label.setText(f"Size {percent}%")
        self.smaller_button.setEnabled(self._window_scale > minimum_scale + 0.01)
        self.larger_button.setEnabled(self._window_scale < maximum_scale - 0.01)
        if hasattr(self, "smaller_action"):
            self.smaller_action.setEnabled(self.smaller_button.isEnabled())
            self.larger_action.setEnabled(self.larger_button.isEnabled())

    def _handle_always_on_top_toggled(self, enabled: bool) -> None:
        if enabled == self._always_on_top:
            self._sync_always_on_top_ui(enabled)
            return
        self.set_always_on_top(enabled, emit_signal=True)

    def _update_window_layout(self) -> None:
        self.background_label.setGeometry(0, 0, self.width(), self.height())
        self.overlay_panel.setGeometry(self._overlay_rect())
        self._apply_frame(self.current_frame_index)

    def _default_scale(self) -> float:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return 1.0
        available = screen.availableGeometry()
        width_ratio = (available.width() * 0.88) / self.design_size.width()
        height_ratio = (available.height() * 0.88) / self.design_size.height()
        return min(width_ratio, height_ratio, 1.0)

    def _scale_bounds(self) -> tuple[float, float]:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return (0.35, 1.25)
        available = screen.availableGeometry()
        max_scale = min(
            (available.width() * 0.96) / self.design_size.width(),
            (available.height() * 0.96) / self.design_size.height(),
            1.6,
        )
        max_scale = max(0.3, max_scale)
        min_scale = min(0.35, max_scale)
        return (min_scale, max_scale)

    def _clamp_scale(self, scale: float) -> float:
        minimum_scale, maximum_scale = self._scale_bounds()
        return max(minimum_scale, min(maximum_scale, scale if scale > 0 else self._default_scale()))

    def _size_for_scale(self, scale: float) -> QSize:
        clamped = self._clamp_scale(scale)
        return QSize(
            max(220, int(self.design_size.width() * clamped)),
            max(150, int(self.design_size.height() * clamped)),
        )

    def _resize_handle_rect(self) -> QRect:
        return QRect(
            max(0, self.width() - self._resize_handle_size),
            max(0, self.height() - self._resize_handle_size),
            self._resize_handle_size,
            self._resize_handle_size,
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
