from __future__ import annotations

import sys

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from openclaw_skins.config import APP_NAME, APP_VENDOR, DEFAULT_SKIN_ID
from openclaw_skins.controller import OpenClawController
from openclaw_skins.resources import resource_path
from openclaw_skins.settings import AppSettingsStore
from openclaw_skins.skins import SkinCatalog
from openclaw_skins.window import SkinHostWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_VENDOR)
    app.setStyle("Fusion")
    _set_windows_app_id()

    icon_path = resource_path("assets", "icons", "openclaw-skins.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    settings_store = AppSettingsStore()
    catalog = SkinCatalog()
    skins = catalog.all()
    if not skins:
        raise RuntimeError("No skin manifests were found.")

    settings = settings_store.settings
    manifest = skins.get(settings.selected_skin) or skins.get(DEFAULT_SKIN_ID) or next(iter(skins.values()))
    controller = OpenClawController(settings_store)
    window = SkinHostWindow(
        manifest=manifest,
        icon_path=icon_path,
        always_on_top=settings.always_on_top,
    )

    controller.connection_state_changed.connect(window.apply_connection_state)
    controller.service_status_changed.connect(window.apply_service_status)
    controller.busy_changed.connect(window.set_busy)
    controller.feedback_changed.connect(window.show_feedback)
    controller.action_running_changed.connect(window.set_action_running)
    window.refresh_requested.connect(controller.refresh)
    window.restart_requested.connect(controller.restart_gateway)
    window.always_on_top_toggled.connect(controller.set_always_on_top)
    app.aboutToQuit.connect(window.prepare_to_quit)
    app.aboutToQuit.connect(controller.shutdown)
    app.aboutToQuit.connect(lambda: controller.save_window_position(window.x(), window.y()))

    if settings.window_position is not None:
        window.move(settings.window_position.x, settings.window_position.y)
    else:
        _center_window(window)

    window.show()
    controller.start()
    return app.exec()


def _center_window(window: SkinHostWindow) -> None:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    geometry = screen.availableGeometry()
    x = geometry.x() + (geometry.width() - window.width()) // 2
    y = geometry.y() + (geometry.height() - window.height()) // 2
    window.move(x, y)


def _set_windows_app_id() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenClawSkins.OpenClawSkins")
    except Exception:
        return
