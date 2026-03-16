from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    font_family: str = "Segoe UI"
    panel_background_rgba: str = "rgba(9, 18, 31, 204)"
    panel_border_rgba: str = "rgba(255, 223, 189, 118)"
    text: str = "#FFF4E7"
    text_muted: str = "#D8DDE6"
    accent: str = "#E98A4B"
    accent_hover: str = "#F7A565"
    success: str = "#51B36E"
    danger: str = "#D26452"
    warning: str = "#F3C563"


def build_stylesheet(theme: ThemeTokens) -> str:
    return f"""
    QWidget#RootWindow {{
        background: transparent;
        color: {theme.text};
        font-family: "{theme.font_family}";
    }}
    QFrame#OverlayPanel {{
        background: {theme.panel_background_rgba};
        border: 1px solid {theme.panel_border_rgba};
        border-radius: 30px;
    }}
    QLabel#PanelTitle {{
        color: {theme.text};
        font-size: 32px;
        font-weight: 800;
    }}
    QLabel#StatusLabel {{
        color: {theme.text};
        font-size: 22px;
        font-weight: 700;
    }}
    QLabel#DetailLabel {{
        color: {theme.text_muted};
        font-size: 17px;
    }}
    QLabel#FeedbackLabel {{
        color: {theme.warning};
        font-size: 15px;
        font-weight: 600;
    }}
    QLabel#ScaleLabel {{
        color: {theme.text_muted};
        font-size: 14px;
        font-weight: 600;
    }}
    QPushButton {{
        background: rgba(255, 255, 255, 12);
        color: {theme.text};
        border: 1px solid rgba(255, 255, 255, 24);
        border-radius: 16px;
        font-size: 15px;
        font-weight: 700;
        min-height: 50px;
        padding: 10px 18px;
    }}
    QPushButton:hover {{
        border-color: rgba(255, 255, 255, 56);
        background: rgba(255, 255, 255, 16);
    }}
    QPushButton:disabled {{
        color: rgba(255, 255, 255, 110);
        border-color: rgba(255, 255, 255, 26);
        background: rgba(255, 255, 255, 8);
    }}
    QPushButton#PrimaryButton {{
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 {theme.accent}, stop: 1 #C55D34);
        border: 1px solid rgba(255, 233, 214, 128);
        color: #FFF8F1;
    }}
    QPushButton#PrimaryButton:hover {{
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 {theme.accent_hover}, stop: 1 #DE7143);
        border-color: rgba(255, 245, 230, 180);
    }}
    QPushButton#SecondaryButton {{
        background: rgba(255, 255, 255, 14);
        border: 1px solid rgba(255, 255, 255, 42);
    }}
    QPushButton#SecondaryButton:hover {{
        background: rgba(255, 255, 255, 20);
        border-color: rgba(255, 255, 255, 78);
    }}
    QPushButton#UtilityButton {{
        min-height: 38px;
        min-width: 38px;
        padding: 6px 12px;
        border-radius: 13px;
        font-size: 14px;
        font-weight: 700;
        background: rgba(255, 255, 255, 10);
        border: 1px solid rgba(255, 255, 255, 34);
    }}
    QCheckBox {{
        color: {theme.text};
        font-size: 15px;
        spacing: 10px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid rgba(255, 255, 255, 55);
        background: rgba(255, 255, 255, 18);
    }}
    QCheckBox::indicator:checked {{
        background: {theme.accent};
        border-color: {theme.accent_hover};
    }}
    """
