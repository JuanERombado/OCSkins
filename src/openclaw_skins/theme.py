from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    font_family: str = "Segoe UI"
    panel_background_rgba: str = "rgba(10, 15, 24, 188)"
    panel_border_rgba: str = "rgba(255, 231, 205, 150)"
    text: str = "#FFF4E7"
    text_muted: str = "#F0DDCB"
    accent: str = "#F08F4B"
    accent_hover: str = "#FDB271"
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
        border: 2px solid {theme.panel_border_rgba};
        border-radius: 28px;
    }}
    QLabel#PanelTitle {{
        color: {theme.text};
        font-size: 30px;
        font-weight: 700;
    }}
    QLabel#StatusLabel {{
        color: {theme.text};
        font-size: 22px;
        font-weight: 700;
    }}
    QLabel#DetailLabel {{
        color: {theme.text_muted};
        font-size: 16px;
    }}
    QLabel#FeedbackLabel {{
        color: {theme.warning};
        font-size: 15px;
        font-weight: 600;
    }}
    QLabel#ScaleLabel {{
        color: {theme.text_muted};
        font-size: 15px;
        font-weight: 600;
    }}
    QPushButton {{
        background: rgba(255, 255, 255, 22);
        color: {theme.text};
        border: 1px solid rgba(255, 255, 255, 40);
        border-radius: 14px;
        font-size: 15px;
        font-weight: 600;
        min-height: 46px;
        padding: 10px 18px;
    }}
    QPushButton:hover {{
        border-color: {theme.accent_hover};
    }}
    QPushButton:disabled {{
        color: rgba(255, 255, 255, 110);
        border-color: rgba(255, 255, 255, 26);
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
